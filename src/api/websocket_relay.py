"""Redis PubSub → WebSocket relay for real-time event delivery.

Subscribes to Redis PubSub channel patterns for scanner, position monitor,
AI, and notification events published by Celery workers, then relays them
to the appropriate Socket.IO user rooms.

Channel naming convention (published by workers):
- ai:signal_analysis:{user_id}
- ai:exit_recommendation:{user_id}
- ai:market_narrative:{user_id}
- ai:risk_warnings:{user_id}
- monitor:threshold_warning:{user_id}
- monitor:status:{user_id}
- scanner:signal:{user_id}
- scanner:signal_detected:{user_id}
- scanner:signal_expired:{user_id}
- scanner:consolidation:{user_id}
- scanner:consolidation_update:{user_id}
- position:monitor:{user_id}
- position:exit_condition:{user_id}
- position:auto_exit:{user_id}
- notification:{user_id}

Requirements covered: 2.4, 4.7, 7.2, 11.2-11.5
"""

import asyncio
import json
import logging
import os
from typing import Optional, Tuple

import redis.asyncio as aioredis

from src.api.websocket import sio

logger = logging.getLogger(__name__)

# --- Channel pattern definitions ---
# These patterns match all user-specific channels published by workers.
CHANNEL_PATTERNS = [
    "ai:*",
    "monitor:*",
    "scanner:*",
    "position:*",
    "notification:*",
]

# --- Channel-to-event mapping ---
# Maps the channel prefix (before the user_id) to a Socket.IO event name.
CHANNEL_EVENT_MAP: dict[str, str] = {
    "ai:signal_analysis": "ai_analysis_result",
    "ai:exit_recommendation": "ai_analysis_result",
    "ai:market_narrative": "ai_market_update",
    "ai:risk_warnings": "ai_risk_warning",
    "monitor:threshold_warning": "threshold_warning",
    "monitor:status": "monitor_status",
    "scanner:signal": "signal_detected",
    "scanner:signal_detected": "signal_detected",
    "scanner:signal_expired": "signal_expired",
    "scanner:consolidation": "consolidation_update",
    "scanner:consolidation_update": "consolidation_update",
    "position:monitor": "position_monitor_update",
    "position:exit_condition": "exit_condition_update",
    "position:auto_exit": "auto_exit_triggered",
    "notification": "notification",
}


def parse_channel(channel: str) -> Optional[Tuple[str, str]]:
    """Parse a Redis PubSub channel name to extract the event prefix and user_id.

    Channel format examples:
        - "ai:signal_analysis:42" → ("ai:signal_analysis", "42")
        - "notification:7" → ("notification", "7")
        - "position:auto_exit:100" → ("position:auto_exit", "100")

    Args:
        channel: The full Redis channel name.

    Returns:
        Tuple of (channel_prefix, user_id) or None if the channel
        doesn't match expected format.
    """
    if not channel:
        return None

    # The user_id is always the last segment after the final ':'
    # For "notification:{user_id}", split gives ["notification", "{user_id}"]
    # For "ai:signal_analysis:{user_id}", split gives ["ai", "signal_analysis", "{user_id}"]
    parts = channel.split(":")
    if len(parts) < 2:
        return None

    user_id = parts[-1]

    # Validate user_id is numeric
    if not user_id.isdigit():
        return None

    # The channel prefix is everything before the last ":"
    channel_prefix = ":".join(parts[:-1])
    return (channel_prefix, user_id)


def get_event_name(channel_prefix: str) -> Optional[str]:
    """Map a channel prefix to a Socket.IO event name.

    Args:
        channel_prefix: The channel prefix without user_id (e.g., "ai:signal_analysis").

    Returns:
        The Socket.IO event name, or None if no mapping exists.
    """
    return CHANNEL_EVENT_MAP.get(channel_prefix)


async def _handle_message(channel: str, data: str) -> None:
    """Process a single PubSub message and relay to Socket.IO.

    Args:
        channel: The Redis channel the message was received on.
        data: The raw message data (expected to be JSON).
    """
    parsed = parse_channel(channel)
    if parsed is None:
        logger.debug("Ignoring message on unrecognized channel: %s", channel)
        return

    channel_prefix, user_id = parsed
    event_name = get_event_name(channel_prefix)

    if event_name is None:
        logger.debug("No event mapping for channel prefix: %s", channel_prefix)
        return

    # Parse the JSON payload
    try:
        payload = json.loads(data)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Invalid JSON on channel '%s': %s", channel, e)
        return

    # Emit to the user's Socket.IO room
    room = f"user:{user_id}"
    try:
        await sio.emit(event_name, payload, room=room)
        logger.debug(
            "Relayed event '%s' to room '%s' from channel '%s'",
            event_name,
            room,
            channel,
        )
    except Exception as e:
        logger.error(
            "Failed to emit event '%s' to room '%s': %s",
            event_name,
            room,
            e,
        )


async def run_pubsub_relay(redis_url: Optional[str] = None) -> None:
    """Main relay loop: subscribe to Redis PubSub and relay to Socket.IO.

    This function runs indefinitely, reconnecting on errors with
    exponential backoff. It should be started as an asyncio background task.

    Args:
        redis_url: Redis connection URL. Defaults to REDIS_URL env var.
    """
    url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    backoff = 1  # Initial backoff in seconds
    max_backoff = 30  # Maximum backoff

    while True:
        redis_conn = None
        pubsub = None
        try:
            logger.info("Connecting to Redis PubSub relay at %s", url)
            redis_conn = aioredis.from_url(url, decode_responses=True)

            # Verify connectivity
            await redis_conn.ping()
            logger.info("Redis PubSub relay connected successfully")

            pubsub = redis_conn.pubsub()

            # Subscribe to all channel patterns
            await pubsub.psubscribe(*CHANNEL_PATTERNS)
            logger.info(
                "Subscribed to Redis PubSub patterns: %s", CHANNEL_PATTERNS
            )

            # Reset backoff on successful connection
            backoff = 1

            # Listen for messages
            async for message in pubsub.listen():
                if message["type"] == "pmessage":
                    channel = message["channel"]
                    data = message["data"]
                    await _handle_message(channel, data)

        except asyncio.CancelledError:
            logger.info("Redis PubSub relay task cancelled, shutting down")
            break
        except Exception as e:
            logger.error(
                "Redis PubSub relay error: %s. Reconnecting in %ds...",
                e,
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
        finally:
            # Clean up connections
            if pubsub is not None:
                try:
                    await pubsub.punsubscribe(*CHANNEL_PATTERNS)
                    await pubsub.close()
                except Exception:
                    pass
            if redis_conn is not None:
                try:
                    await redis_conn.close()
                except Exception:
                    pass


# --- Background task handle ---
_relay_task: Optional[asyncio.Task] = None


async def start_pubsub_relay() -> None:
    """Start the PubSub relay as a background asyncio task.

    Should be called during FastAPI app startup (lifespan event).
    """
    global _relay_task
    if _relay_task is not None and not _relay_task.done():
        logger.warning("PubSub relay task already running")
        return

    _relay_task = asyncio.create_task(run_pubsub_relay())
    logger.info("Redis PubSub relay background task started")


async def stop_pubsub_relay() -> None:
    """Stop the PubSub relay background task.

    Should be called during FastAPI app shutdown (lifespan event).
    """
    global _relay_task
    if _relay_task is None or _relay_task.done():
        return

    _relay_task.cancel()
    try:
        await _relay_task
    except asyncio.CancelledError:
        pass
    _relay_task = None
    logger.info("Redis PubSub relay background task stopped")
