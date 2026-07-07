"""Celery task for periodic market data updates.

Schedules the MarketDataWorker to fetch spot prices for all configured
instruments every 3-5 seconds (scheduled at 4s via Celery Beat).
Also fetches option chain data at a reduced frequency (every ~5 cycles)
since option chains are heavier API calls and don't require 3-5s updates.

Requirements covered:
- 1.6.1: Fetch spot prices for configured instruments every 3-5 seconds
- 1.6.2: Fetch option chain data for NIFTY and BANKNIFTY
- 1.6.5: Share market data across all users
- 1.6.8: Continue processing other symbols if one symbol fails
"""

import logging
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

from src.cache.redis_client import get_redis_client
from src.workers.celery_app import celery_app
from src.workers.market_data_worker import DEFAULT_INSTRUMENTS, MarketDataWorker

logger = logging.getLogger(__name__)

# Option chain symbols to fetch (Requirement 1.6.2)
OPTION_CHAIN_SYMBOLS: List[str] = ["NIFTY", "BANKNIFTY"]

# Fetch option chains every N cycles (~20 seconds at 4s interval)
OPTION_CHAIN_FETCH_INTERVAL: int = 5

# Module-level counter for option chain fetch frequency
_cycle_counter: int = 0


@celery_app.task(name="src.workers.market_data_task.update_market_data")
def update_market_data() -> Dict:
    """Celery task: Fetch and cache market data for all configured instruments.

    Processes ALL configured instruments from DEFAULT_INSTRUMENTS:
    1. Fetches spot prices for every configured instrument (NIFTY, BANKNIFTY)
    2. Stores ticks for VWAP calculation
    3. Computes VWAP from recent ticks
    4. Caches aggregated market data (spot + VWAP) per symbol
    5. Periodically fetches option chain data (every OPTION_CHAIN_FETCH_INTERVAL cycles)

    Continues processing if individual symbols fail (Requirement 1.6.8).
    Data is shared across all users (Requirement 1.6.5).

    Returns:
        A dict summarizing the run:
            - "status" (str): "success" or "partial" or "error"
            - "prices" (Dict[str, float]): Successfully fetched prices
            - "errors" (Dict[str, str]): Errors keyed by symbol
            - "timestamp" (str): ISO format timestamp of the run
            - "symbols_processed" (int): Count of successful symbols
            - "symbols_failed" (int): Count of failed symbols
            - "instruments_configured" (int): Total configured instruments count
            - "option_chains_fetched" (bool): Whether option chains were fetched this cycle
    """
    global _cycle_counter
    timestamp = datetime.now().isoformat()

    # Top-level safety net: the Celery task must NEVER raise an exception.
    # All code paths below are individually guarded, but this outer try/except
    # ensures that even truly unexpected errors (e.g., serialization bugs,
    # global state corruption) are caught, logged, and returned as a dict.
    try:
        return _execute_market_data_update(timestamp)
    except Exception as e:
        logger.error(
            "Unexpected top-level error in update_market_data task: %s (type=%s)",
            e,
            type(e).__name__,
        )
        return {
            "status": "error",
            "prices": {},
            "errors": {"_system": f"Unexpected error: {e}"},
            "timestamp": timestamp,
            "symbols_processed": 0,
            "symbols_failed": 0,
            "instruments_configured": len(DEFAULT_INSTRUMENTS),
            "option_chains_fetched": False,
        }


def _execute_market_data_update(timestamp: str) -> Dict:
    """Internal implementation of the market data update logic.

    Separated from the task function to allow the task's top-level
    try/except to catch any unexpected errors without nesting.
    """
    global _cycle_counter

    # Get shared dependencies
    try:
        redis_client = get_redis_client()
    except Exception as e:
        logger.error("Failed to get Redis client: %s", e)
        return {
            "status": "error",
            "prices": {},
            "errors": {"_system": str(e)},
            "timestamp": timestamp,
            "symbols_processed": 0,
            "symbols_failed": 0,
            "instruments_configured": len(DEFAULT_INSTRUMENTS),
            "option_chains_fetched": False,
        }

    try:
        kite_client = _get_shared_kite_client()
    except Exception as e:
        logger.error("Failed to get Kite client: %s", e)
        return {
            "status": "error",
            "prices": {},
            "errors": {"_system": str(e)},
            "timestamp": timestamp,
            "symbols_processed": 0,
            "symbols_failed": 0,
            "instruments_configured": len(DEFAULT_INSTRUMENTS),
            "option_chains_fetched": False,
        }

    # Create worker with all configured instruments and fetch spot prices
    worker = MarketDataWorker(
        kite_client=kite_client,
        redis_client=redis_client,
    )

    # Fetch spot prices for ALL configured instruments (Requirement 1.6.1)
    result = worker.fetch_all_spot_prices()
    prices = result["prices"]
    errors = result["errors"]

    # Store tick and cache market data for each successfully fetched symbol
    for symbol, price in prices.items():
        try:
            # Store tick for VWAP calculation (volume=0 since LTP doesn't give volume)
            worker.store_tick(symbol, price, volume=0)
        except Exception as e:
            logger.warning("Failed to store tick for %s: %s", symbol, e)

        try:
            # Compute VWAP from recent ticks (Requirement 1.6.3)
            vwap = worker.compute_vwap(symbol)

            # Cache aggregated market data (Requirement 1.6.4)
            market_data: Dict = {
                "spot": price,
                "vwap": vwap,
                "timestamp": timestamp,
            }
            worker.cache_market_data(symbol, market_data)
        except Exception as e:
            logger.warning("Failed to cache market data for %s: %s", symbol, e)

    # Fetch option chains periodically (Requirement 1.6.2)
    # Option chains are heavier API calls and don't need 3-5s refresh
    option_chains_fetched = False
    _cycle_counter += 1

    if _cycle_counter >= OPTION_CHAIN_FETCH_INTERVAL:
        _cycle_counter = 0
        option_chains_fetched = True
        expiry = _get_current_expiry()

        if expiry:
            try:
                chain_result = worker.fetch_all_option_chains(
                    expiry=expiry, symbols=OPTION_CHAIN_SYMBOLS
                )
                chains = chain_result.get("chains", {})
                chain_errors = chain_result.get("errors", {})

                # Cache option chain data for each symbol
                for symbol, chain in chains.items():
                    try:
                        chain_cache_data: Dict = {
                            "option_chain": chain,
                            "expiry": expiry,
                            "timestamp": timestamp,
                        }
                        worker.cache_market_data(
                            f"{symbol}_OPTIONS", chain_cache_data
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to cache option chain for %s: %s", symbol, e
                        )

                if chain_errors:
                    logger.warning(
                        "Option chain fetch errors: %s",
                        {k: v.get("error", str(v)) for k, v in chain_errors.items()},
                    )
            except Exception as e:
                logger.warning("Failed to fetch option chains: %s", e)
        else:
            logger.info("No expiry date available, skipping option chain fetch")

    # Determine overall status
    symbols_processed = len(prices)
    symbols_failed = len(errors)

    if symbols_failed == 0:
        status = "success"
    elif symbols_processed > 0:
        status = "partial"
    else:
        status = "error"

    logger.info(
        "Market data update: %s (%d/%d symbols fetched, options=%s)",
        status,
        symbols_processed,
        symbols_processed + symbols_failed,
        option_chains_fetched,
    )

    return {
        "status": status,
        "prices": prices,
        "errors": {k: v.get("error", str(v)) if isinstance(v, dict) else str(v) for k, v in errors.items()},
        "timestamp": timestamp,
        "symbols_processed": symbols_processed,
        "symbols_failed": symbols_failed,
        "instruments_configured": len(DEFAULT_INSTRUMENTS),
        "option_chains_fetched": option_chains_fetched,
    }


def _get_current_expiry() -> Optional[str]:
    """Get the current/nearest weekly expiry date for option chain fetching.

    Returns the next Thursday (NSE weekly expiry day) in YYYY-MM-DD format.
    If today is Thursday, returns today's date.

    Returns:
        Expiry date string in YYYY-MM-DD format, or None if calculation fails.
    """
    try:
        today = date.today()
        # Thursday = 3 in Python's weekday() (Mon=0, Tue=1, ..., Thu=3)
        days_until_thursday = (3 - today.weekday()) % 7
        if days_until_thursday == 0:
            # Today is Thursday - use today
            expiry_date = today
        else:
            expiry_date = today + timedelta(days=days_until_thursday)
        return expiry_date.isoformat()
    except Exception as e:
        logger.error("Failed to compute current expiry date: %s", e)
        return None


def _get_shared_kite_client():
    """Get a shared Kite client for market data fetching.

    The market data worker uses a shared Kite client (not user-specific)
    since market data is shared across all users. This uses a system-level
    API key and access token from environment variables.

    Returns:
        A configured KiteConnect instance.

    Raises:
        RuntimeError: If Kite credentials are not configured.
    """
    from kiteconnect import KiteConnect

    api_key = os.environ.get("KITE_API_KEY")
    access_token = os.environ.get("KITE_ACCESS_TOKEN")

    if not api_key:
        raise RuntimeError(
            "KITE_API_KEY environment variable is required for market data worker"
        )
    if not access_token:
        raise RuntimeError(
            "KITE_ACCESS_TOKEN environment variable is required for market data worker"
        )

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite
