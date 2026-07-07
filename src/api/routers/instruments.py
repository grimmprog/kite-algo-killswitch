"""Instruments API: Option Chain, Search, and Quotes.

Endpoints:
- GET /api/v1/instruments/option-chain — NIFTY/BANKNIFTY option chain with live quotes
- GET /api/v1/instruments/search — Search instruments by name/symbol
- GET /api/v1/instruments/quote — Get live quotes for specific symbols
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user, get_db, get_redis
from src.broker.token_encryption import TokenEncryption, TokenEncryptionError
from src.cache.redis_client import RedisClient
from src.database.models.broker_connection import BrokerConnection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/instruments", tags=["instruments"])

# Redis cache keys and TTLs
INSTRUMENTS_CACHE_KEY = "instruments:nfo:all"
INSTRUMENTS_NSE_CACHE_KEY = "instruments:nse:all"
OPTION_CHAIN_CACHE_PREFIX = "instruments:optionchain:"
INSTRUMENTS_TTL = 86400  # 24 hours
OPTION_CHAIN_TTL = 5  # 5 seconds


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class OptionChainEntry(BaseModel):
    strike: float
    ce_ltp: float = 0.0
    ce_change: float = 0.0
    ce_oi: int = 0
    ce_volume: int = 0
    ce_symbol: str = ""
    ce_bid: float = 0.0
    ce_ask: float = 0.0
    pe_ltp: float = 0.0
    pe_change: float = 0.0
    pe_oi: int = 0
    pe_volume: int = 0
    pe_symbol: str = ""
    pe_bid: float = 0.0
    pe_ask: float = 0.0


class OptionChainResponse(BaseModel):
    index: str
    spot_price: float
    expiry: str
    lot_size: int
    strikes: List[OptionChainEntry]


class InstrumentSearchResult(BaseModel):
    tradingsymbol: str
    name: str
    exchange: str
    instrument_type: str
    lot_size: int
    last_price: float = 0.0
    change_percent: float = 0.0


class QuoteItem(BaseModel):
    symbol: str
    ltp: float
    change: float
    change_percent: float
    volume: int
    oi: int = 0


# ---------------------------------------------------------------------------
# Kite session helper (same pattern as account.py)
# ---------------------------------------------------------------------------


def _get_kite_access_token(db: Session, user_id: int) -> str:
    """Resolve Kite access token for the given user."""
    encryption_key = os.environ.get("ENCRYPTION_KEY", "")
    if encryption_key:
        try:
            connection = (
                db.query(BrokerConnection)
                .filter(
                    BrokerConnection.user_id == user_id,
                    BrokerConnection.broker_type == "kite",
                    BrokerConnection.access_token_encrypted.isnot(None),
                )
                .first()
            )

            if connection:
                if connection.token_expiry and connection.token_expiry.replace(
                    tzinfo=timezone.utc
                ) < datetime.now(timezone.utc):
                    logger.warning("Kite token expired for user %d", user_id)
                else:
                    encryptor = TokenEncryption(encryption_key=encryption_key)
                    token = encryptor.decrypt(connection.access_token_encrypted)
                    if token:
                        return token
        except TokenEncryptionError as e:
            logger.error("Failed to decrypt token for user %d: %s", user_id, e)
        except Exception as e:
            logger.error("Database token lookup failed for user %d: %s", user_id, e)

    # Fallback: access_token.txt file
    base_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    token_path = os.path.join(base_dir, "access_token.txt")

    if os.path.exists(token_path):
        try:
            with open(token_path, "r") as f:
                token = f.read().strip()
                if token:
                    return token
        except IOError as e:
            logger.error("Failed to read access_token.txt: %s", e)

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Kite session not available. Please reconnect your broker.",
    )


def _get_kite_client(access_token: str):
    """Create an authenticated KiteConnect client."""
    from kiteconnect import KiteConnect

    api_key = os.environ.get("KITE_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="KITE_API_KEY not configured",
        )

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_nfo_instruments(kite, redis: RedisClient) -> list:
    """Get NFO instruments, cached in Redis for 24h."""
    cached = redis.get(INSTRUMENTS_CACHE_KEY)
    if cached:
        return json.loads(cached)

    instruments = kite.instruments("NFO")
    # Convert to serializable dicts
    data = []
    for inst in instruments:
        data.append({
            "tradingsymbol": inst.get("tradingsymbol", ""),
            "name": inst.get("name", ""),
            "exchange": inst.get("exchange", "NFO"),
            "instrument_type": inst.get("instrument_type", ""),
            "strike": float(inst.get("strike", 0)),
            "expiry": inst.get("expiry").strftime("%Y-%m-%d") if inst.get("expiry") else "",
            "lot_size": int(inst.get("lot_size", 0)),
            "instrument_token": inst.get("instrument_token", ""),
            "segment": inst.get("segment", ""),
        })

    redis.set(INSTRUMENTS_CACHE_KEY, json.dumps(data), ttl=INSTRUMENTS_TTL)
    return data


def _get_nse_instruments(kite, redis: RedisClient) -> list:
    """Get NSE instruments, cached in Redis for 24h."""
    cached = redis.get(INSTRUMENTS_NSE_CACHE_KEY)
    if cached:
        return json.loads(cached)

    instruments = kite.instruments("NSE")
    data = []
    for inst in instruments:
        data.append({
            "tradingsymbol": inst.get("tradingsymbol", ""),
            "name": inst.get("name", ""),
            "exchange": inst.get("exchange", "NSE"),
            "instrument_type": inst.get("instrument_type", ""),
            "lot_size": int(inst.get("lot_size", 1)),
            "instrument_token": inst.get("instrument_token", ""),
        })

    redis.set(INSTRUMENTS_NSE_CACHE_KEY, json.dumps(data), ttl=INSTRUMENTS_TTL)
    return data


def _find_nearest_expiry(instruments: list, index_name: str) -> str:
    """Find the nearest expiry for a given index from the instruments list."""
    today = datetime.now().strftime("%Y-%m-%d")
    expiries = set()

    for inst in instruments:
        if inst["name"] == index_name and inst["instrument_type"] in ("CE", "PE"):
            exp = inst["expiry"]
            if exp and exp >= today:
                expiries.add(exp)

    if not expiries:
        return ""

    return min(expiries)


# ---------------------------------------------------------------------------
# GET /api/v1/instruments/option-chain
# ---------------------------------------------------------------------------


@router.get("/option-chain", response_model=OptionChainResponse)
async def get_option_chain(
    index: str = Query("NIFTY", description="Index name: NIFTY or BANKNIFTY"),
    expiry: str = Query("nearest", description="Expiry date (YYYY-MM-DD) or 'nearest'"),
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get option chain data for NIFTY or BANKNIFTY.

    Returns strikes with CE/PE data including LTP, OI, volume, bid, ask.
    Results are cached for 5 seconds.
    """
    index = index.upper()
    if index not in ("NIFTY", "BANKNIFTY", "SENSEX"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Index must be NIFTY, BANKNIFTY, or SENSEX",
        )

    # Check cache first
    cache_key = f"{OPTION_CHAIN_CACHE_PREFIX}{index}:{expiry}"
    cached = redis.get(cache_key)
    if cached:
        return OptionChainResponse(**json.loads(cached))

    access_token = _get_kite_access_token(db, user_id)
    kite = _get_kite_client(access_token)

    # Get instruments
    nfo_instruments = _get_nfo_instruments(kite, redis)

    # Determine expiry
    if expiry == "nearest":
        expiry_date = _find_nearest_expiry(nfo_instruments, index)
    else:
        expiry_date = expiry

    if not expiry_date:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No expiry found for {index}",
        )

    # Filter instruments for this index + expiry
    ce_instruments = {}
    pe_instruments = {}
    lot_size = 0

    for inst in nfo_instruments:
        if inst["name"] != index or inst["expiry"] != expiry_date:
            continue
        if inst["instrument_type"] == "CE":
            ce_instruments[inst["strike"]] = inst
            if not lot_size:
                lot_size = inst["lot_size"]
        elif inst["instrument_type"] == "PE":
            pe_instruments[inst["strike"]] = inst
            if not lot_size:
                lot_size = inst["lot_size"]

    # Get all strikes
    all_strikes = sorted(set(list(ce_instruments.keys()) + list(pe_instruments.keys())))

    if not all_strikes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No option data found for {index} expiry {expiry_date}",
        )

    # Get spot price using ltp() (works without paid Quote API)
    spot_map = {"NIFTY": "NSE:NIFTY 50", "BANKNIFTY": "NSE:NIFTY BANK", "SENSEX": "BSE:SENSEX"}
    spot_symbol = spot_map.get(index, "NSE:NIFTY 50")
    try:
        spot_data = kite.ltp([spot_symbol])
        spot_price = spot_data[spot_symbol]["last_price"] if spot_symbol in spot_data else 0
    except Exception as e:
        logger.warning("Failed to get spot price for %s: %s", spot_symbol, e)
        spot_price = 0

    # Determine ATM strike range — show ~20 strikes around ATM
    atm_strike = min(all_strikes, key=lambda s: abs(s - spot_price)) if spot_price else all_strikes[len(all_strikes) // 2]
    strike_gap = all_strikes[1] - all_strikes[0] if len(all_strikes) > 1 else 50
    range_strikes = [s for s in all_strikes if abs(s - atm_strike) <= strike_gap * 15]

    if not range_strikes:
        range_strikes = all_strikes[:30]

    # Get live LTP in batches of 200 (uses ltp() which doesn't need paid Quote API)
    symbols_to_quote = []
    for strike in range_strikes:
        if strike in ce_instruments:
            symbols_to_quote.append(f"NFO:{ce_instruments[strike]['tradingsymbol']}")
        if strike in pe_instruments:
            symbols_to_quote.append(f"NFO:{pe_instruments[strike]['tradingsymbol']}")

    quotes = {}
    batch_size = 200
    for i in range(0, len(symbols_to_quote), batch_size):
        batch = symbols_to_quote[i : i + batch_size]
        try:
            batch_ltp = kite.ltp(batch)
            quotes.update(batch_ltp)
        except Exception as e:
            logger.error("Failed to fetch LTP batch: %s", e)

    # Build response
    strikes_data = []
    for strike in range_strikes:
        entry = OptionChainEntry(strike=strike)

        if strike in ce_instruments:
            ce_sym = ce_instruments[strike]["tradingsymbol"]
            quote_key = f"NFO:{ce_sym}"
            entry.ce_symbol = ce_sym
            if quote_key in quotes:
                entry.ce_ltp = quotes[quote_key].get("last_price", 0) or 0

        if strike in pe_instruments:
            pe_sym = pe_instruments[strike]["tradingsymbol"]
            quote_key = f"NFO:{pe_sym}"
            entry.pe_symbol = pe_sym
            if quote_key in quotes:
                entry.pe_ltp = quotes[quote_key].get("last_price", 0) or 0

        strikes_data.append(entry)

    response = OptionChainResponse(
        index=index,
        spot_price=spot_price,
        expiry=expiry_date,
        lot_size=lot_size or 50,
        strikes=strikes_data,
    )

    # Cache for 5 seconds
    redis.set(cache_key, json.dumps(response.model_dump()), ttl=OPTION_CHAIN_TTL)

    return response


# ---------------------------------------------------------------------------
# GET /api/v1/instruments/expiries
# ---------------------------------------------------------------------------


@router.get("/expiries")
async def get_expiries(
    index: str = Query("NIFTY", description="Index: NIFTY, BANKNIFTY, or SENSEX"),
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get available expiry dates for an index.

    Returns sorted list of upcoming expiry dates.
    """
    access_token = _get_kite_access_token(db, user_id)
    kite = _get_kite_client(access_token)

    index = index.upper()
    nfo_instruments = _get_nfo_instruments(kite, redis)

    today = datetime.now().strftime("%Y-%m-%d")
    expiries = set()

    for inst in nfo_instruments:
        if inst["name"] == index and inst["instrument_type"] in ("CE", "PE"):
            exp = inst["expiry"]
            if exp and exp >= today:
                expiries.add(exp)

    return {"index": index, "expiries": sorted(expiries)[:12]}


# ---------------------------------------------------------------------------
# GET /api/v1/instruments/search
# ---------------------------------------------------------------------------


@router.get("/search", response_model=List[InstrumentSearchResult])
async def search_instruments(
    q: str = Query(..., min_length=1, description="Search query"),
    exchange: str = Query("NSE", description="Exchange: NSE, NFO, BSE"),
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Search instruments by name or trading symbol.

    Returns top 20 matches from the cached instruments list.
    """
    access_token = _get_kite_access_token(db, user_id)
    kite = _get_kite_client(access_token)

    exchange = exchange.upper()
    query = q.upper().strip()

    if exchange == "NFO":
        instruments = _get_nfo_instruments(kite, redis)
    else:
        instruments = _get_nse_instruments(kite, redis)

    # Filter by query match (tradingsymbol or name)
    results = []
    for inst in instruments:
        symbol = inst.get("tradingsymbol", "").upper()
        name = inst.get("name", "").upper()

        if query in symbol or query in name:
            results.append(InstrumentSearchResult(
                tradingsymbol=inst.get("tradingsymbol", ""),
                name=inst.get("name", ""),
                exchange=inst.get("exchange", exchange),
                instrument_type=inst.get("instrument_type", "EQ"),
                lot_size=inst.get("lot_size", 1),
            ))

        if len(results) >= 20:
            break

    # Try to get live prices for top results (limit to avoid too many API calls)
    if results:
        symbols_to_quote = [
            f"{r.exchange}:{r.tradingsymbol}" for r in results[:10]
        ]
        try:
            quotes = kite.quote(symbols_to_quote)
            for r in results[:10]:
                quote_key = f"{r.exchange}:{r.tradingsymbol}"
                if quote_key in quotes:
                    q_data = quotes[quote_key]
                    r.last_price = q_data.get("last_price", 0) or 0
                    net_change = q_data.get("net_change", 0) or 0
                    ohlc = q_data.get("ohlc", {})
                    prev_close = ohlc.get("close", 0) or 0
                    if prev_close:
                        r.change_percent = round((net_change / prev_close) * 100, 2)
        except Exception as e:
            logger.warning("Failed to fetch quotes for search results: %s", e)

    return results


# ---------------------------------------------------------------------------
# GET /api/v1/instruments/quote
# ---------------------------------------------------------------------------


@router.get("/quote", response_model=List[QuoteItem])
async def get_quotes(
    symbols: str = Query(..., description="Comma-separated symbols, e.g. NSE:RELIANCE,NFO:NIFTY24JUL24300CE"),
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get live quotes for specific instruments.

    Symbols should be in exchange:tradingsymbol format.
    """
    access_token = _get_kite_access_token(db, user_id)
    kite = _get_kite_client(access_token)

    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]

    if not symbol_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one symbol is required",
        )

    if len(symbol_list) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 50 symbols per request",
        )

    try:
        quotes = kite.quote(symbol_list)
    except Exception as e:
        logger.error("Failed to fetch quotes: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch quotes from broker: {str(e)}",
        )

    results = []
    for sym in symbol_list:
        if sym in quotes:
            q = quotes[sym]
            net_change = q.get("net_change", 0) or 0
            ohlc = q.get("ohlc", {})
            prev_close = ohlc.get("close", 0) or 0
            change_pct = round((net_change / prev_close) * 100, 2) if prev_close else 0

            results.append(QuoteItem(
                symbol=sym,
                ltp=q.get("last_price", 0) or 0,
                change=net_change,
                change_percent=change_pct,
                volume=q.get("volume", 0) or 0,
                oi=q.get("oi", 0) or 0,
            ))

    return results
