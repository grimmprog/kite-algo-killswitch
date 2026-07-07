"""Signal Pipeline — Wires Scanner → Signal → AI Analysis → WebSocket flow.

This module provides the integration layer that connects:
1. Scanner worker signal detection → SignalService.create_signal (persistence)
2. Signal creation → AI signal analysis trigger (via ai_worker task)
3. Signal creation → Redis PubSub signal_detected event (for WebSocket relay)

The pipeline ensures that when the scanner detects a signal, it is:
- Persisted to the database as a pending signal with countdown
- Queued for AI quality analysis (async, non-blocking)
- Published via Redis PubSub for real-time WebSocket delivery

Requirements covered: 1.1, 4.1-4.7, 18.1
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.cache.redis_client import RedisClient, get_redis_client
from src.services.signal_service import SignalService

logger = logging.getLogger(__name__)

# Redis PubSub channels (must match websocket_relay.py CHANNEL_EVENT_MAP)
SIGNAL_DETECTED_CHANNEL = "scanner:signal:{user_id}"
SIGNAL_EXPIRED_CHANNEL = "scanner:signal_expired:{user_id}"


def process_scanner_signals(
    user_id: int,
    signals: List[Dict[str, Any]],
    db: Session,
    redis_client: RedisClient,
    countdown_seconds: int = 60,
    trigger_ai_analysis: bool = True,
) -> List[Dict[str, Any]]:
    """Process detected scanner signals through the full pipeline.

    For each signal:
    1. Persist via SignalService.create_signal (creates pending signal with TTL)
    2. Trigger AI signal quality analysis (async Celery task)
    3. Publish signal_detected event for WebSocket relay

    This function is called by the scanner worker after it detects signals,
    replacing the direct Redis publish + cache approach with the full
    persistence and notification pipeline.

    Args:
        user_id: The user who owns the signals.
        signals: List of signal dicts from scanner analysis. Each must contain:
            - symbol (str): Trading symbol
            - scan_type (str): "trend_pullback" or "consolidation_breakout"
            - confidence_score (float): 50-100
            - entry_price (float): Suggested entry price
            - stop_loss (float): Stop-loss level
            - target_price (float): Target price
            - max_potential_loss (float): Maximum potential loss
            - metadata (dict, optional): Additional signal context
        db: SQLAlchemy session for database operations.
        redis_client: RedisClient instance for Redis operations.
        countdown_seconds: Signal expiry countdown in seconds (default 60).
        trigger_ai_analysis: Whether to queue AI analysis (default True).

    Returns:
        List of created signal dicts (with id, countdown info, etc.).
    """
    if not signals:
        return []

    signal_service = SignalService(db=db, redis_client=redis_client)
    created_signals = []

    for signal_data in signals:
        try:
            # Normalize signal data for SignalService
            normalized = _normalize_signal_data(signal_data)

            # Step 1: Persist signal via SignalService
            signal_record = signal_service.create_signal(
                user_id=user_id,
                scan_signal_data=normalized,
                countdown_seconds=countdown_seconds,
            )

            # Build the result dict for this signal
            created_signal = {
                "id": signal_record.id,
                "user_id": user_id,
                "symbol": signal_record.symbol,
                "signal_type": signal_record.signal_type,
                "confidence_score": signal_record.confidence_score,
                "entry_price": signal_record.entry_price,
                "stop_loss": signal_record.stop_loss,
                "target_price": signal_record.target_price,
                "max_potential_loss": signal_record.max_potential_loss,
                "status": signal_record.status,
                "countdown_seconds": countdown_seconds,
                "remaining_seconds": countdown_seconds,
                "expires_at": (
                    signal_record.expires_at.isoformat()
                    if signal_record.expires_at
                    else None
                ),
                "created_at": (
                    signal_record.created_at.isoformat()
                    if signal_record.created_at
                    else None
                ),
                "ai_quality_rating": signal_record.ai_quality_rating,
                "ai_warnings": signal_record.ai_warnings,
                "ai_explanation": signal_record.ai_explanation,
            }

            created_signals.append(created_signal)

            # Step 2: Trigger AI signal analysis (non-blocking)
            if trigger_ai_analysis:
                _trigger_ai_analysis(user_id, signal_data, signal_record.id)

            # Step 3: Publish signal_detected event for WebSocket relay
            _publish_signal_detected(user_id, created_signal)

            logger.info(
                "Signal pipeline: created signal %d for user %d (symbol=%s, confidence=%.1f)",
                signal_record.id,
                user_id,
                signal_record.symbol,
                signal_record.confidence_score,
            )

        except Exception as e:
            logger.error(
                "Signal pipeline: failed to process signal for user %d (symbol=%s): %s: %s",
                user_id,
                signal_data.get("symbol", "unknown"),
                type(e).__name__,
                str(e),
            )
            # Continue processing remaining signals
            continue

    return created_signals


def publish_signal_expired(user_id: int, signal_id: int, symbol: str) -> bool:
    """Publish a signal_expired event via Redis PubSub for WebSocket relay.

    Called by the signal expiry worker when a signal's countdown reaches zero.

    Args:
        user_id: The user who owned the signal.
        signal_id: The expired signal's database ID.
        symbol: The trading symbol of the expired signal.

    Returns:
        True if published successfully, False otherwise.
    """
    redis_client = get_redis_client()
    channel = SIGNAL_EXPIRED_CHANNEL.format(user_id=user_id)

    payload = {
        "signal_id": signal_id,
        "user_id": user_id,
        "symbol": symbol,
        "status": "expired",
        "expired_at": datetime.now().isoformat(),
    }

    try:
        redis_client.client.publish(channel, json.dumps(payload, default=str))
        logger.debug(
            "Published signal_expired event for signal %d (user %d)",
            signal_id,
            user_id,
        )
        return True
    except Exception as e:
        logger.error(
            "Failed to publish signal_expired for signal %d: %s: %s",
            signal_id,
            type(e).__name__,
            str(e),
        )
        return False


def _normalize_signal_data(signal_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize scanner output into the format expected by SignalService.create_signal.

    Maps scan_type to signal_type, ensures required fields are present,
    and handles field name differences between ScannerService output and
    SignalService input.

    Args:
        signal_data: Raw signal dict from scanner analysis.

    Returns:
        Normalized dict ready for SignalService.create_signal.
    """
    return {
        "signal_type": signal_data.get("signal_type", signal_data.get("scan_type", "trend_pullback")),
        "symbol": signal_data["symbol"],
        "confidence_score": signal_data["confidence_score"],
        "entry_price": signal_data["entry_price"],
        "stop_loss": signal_data.get("stop_loss", signal_data.get("stop_loss_price", 0)),
        "target_price": signal_data.get("target_price", 0),
        "max_potential_loss": signal_data.get("max_potential_loss", signal_data.get("max_loss", 0)),
        "ai_quality_rating": signal_data.get("ai_quality_rating"),
        "ai_warnings": signal_data.get("ai_warnings"),
        "ai_explanation": signal_data.get("ai_explanation"),
        "metadata": signal_data.get("metadata"),
    }


def _trigger_ai_analysis(
    user_id: int,
    signal_data: Dict[str, Any],
    signal_id: int,
) -> Optional[str]:
    """Trigger AI signal quality analysis via Celery task.

    Queues the analyze_signal_quality task with the signal context.
    This is non-blocking — the analysis runs asynchronously and
    publishes results via Redis PubSub when complete.

    Args:
        user_id: The user who owns the signal.
        signal_data: The raw signal data for AI context.
        signal_id: The persisted signal's database ID (for correlation).

    Returns:
        The Celery task ID if queued successfully, None on failure.
    """
    try:
        from src.workers.celery_app import celery_app

        # Build AI signal context from scanner data
        ai_context = {
            "signal_id": signal_id,
            "symbol": signal_data.get("symbol"),
            "scan_type": signal_data.get("scan_type", signal_data.get("signal_type")),
            "confidence_score": signal_data.get("confidence_score"),
            "entry_price": signal_data.get("entry_price"),
            "stop_loss": signal_data.get("stop_loss"),
            "target_price": signal_data.get("target_price"),
            "metadata": signal_data.get("metadata", {}),
        }

        task = celery_app.send_task(
            "src.workers.ai_worker.analyze_signal_quality",
            args=[user_id, ai_context],
        )

        logger.debug(
            "Queued AI signal analysis for signal %d (user %d): task_id=%s",
            signal_id,
            user_id,
            task.id,
        )
        return task.id

    except Exception as e:
        # AI analysis failure should never block signal pipeline
        logger.warning(
            "Failed to queue AI analysis for signal %d (user %d): %s: %s",
            signal_id,
            user_id,
            type(e).__name__,
            str(e),
        )
        return None


def _publish_signal_detected(user_id: int, signal_data: Dict[str, Any]) -> bool:
    """Publish signal_detected event via Redis PubSub for WebSocket relay.

    The WebSocket relay subscribes to scanner:* patterns and maps
    "scanner:signal:{user_id}" → "signal_detected" Socket.IO event.

    Args:
        user_id: The target user.
        signal_data: The signal payload to broadcast.

    Returns:
        True if published successfully, False otherwise.
    """
    redis_client = get_redis_client()
    channel = SIGNAL_DETECTED_CHANNEL.format(user_id=user_id)

    payload = {
        "user_id": user_id,
        "signal": signal_data,
        "timestamp": datetime.now().isoformat(),
    }

    try:
        redis_client.client.publish(channel, json.dumps(payload, default=str))
        logger.debug(
            "Published signal_detected for signal %s (user %d) on channel '%s'",
            signal_data.get("id"),
            user_id,
            channel,
        )
        return True
    except Exception as e:
        logger.error(
            "Failed to publish signal_detected for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        return False
