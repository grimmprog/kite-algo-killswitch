"""Redis pub/sub subscriber for forwarding events to WebSocket clients.

Subscribes to Redis channels for real-time updates and forwards messages
to connected WebSocket clients via Socket.IO broadcast functions.

Requirements covered:
- 13.3.1: Subscribe to Redis channels (risk, position, order, killswitch)
- 13.3.2: Forward messages to WebSocket clients via broadcast functions
- 11.4: Forward kill switch critical notifications to WebSocket clients

Channels:
- risk_update: Risk metrics changes -> broadcast_risk_update
- position_update: Position changes -> broadcast_position_update
- order_update: Order status changes -> broadcast_order_update
- killswitch_update: Kill switch state changes -> broadcast_killswitch_update
- notifications:* (pattern): Notification events -> broadcast_notification

Message format (JSON):
    {"user_id": int, ...payload}
"""

import json
import logging

import redis.asyncio as aioredis

from src.api.websocket import (
    broadcast_killswitch_update,
    broadcast_notification,
    broadcast_order_update,
    broadcast_position_update,
    broadcast_risk_update,
)

logger = logging.getLogger(__name__)

# Channel-to-handler mapping (exact channels)
CHANNELS = {
    "risk_update": broadcast_risk_update,
    "position_update": broadcast_position_update,
    "order_update": broadcast_order_update,
    "killswitch_update": broadcast_killswitch_update,
}

# Pattern-based channel subscriptions
# Pattern "notifications:*" matches channels like "notifications:42"
PATTERN_CHANNELS = {
    "notifications:*": broadcast_notification,
}


async def start_redis_subscriber(redis_url: str = "redis://localhost:6379/0"):
    """Subscribe to Redis channels and forward events to WebSocket clients.

    Listens indefinitely on all defined channels (both exact and pattern-based).
    When a message arrives, it extracts the user_id and dispatches to the
    appropriate broadcast function.

    For pattern subscriptions (notifications:*), the user_id is extracted from
    the channel name (e.g., "notifications:42" → user_id=42) or from the message
    payload.

    Args:
        redis_url: Redis connection URL. Defaults to localhost.

    Raises:
        Exception: Logs and re-raises connection or parsing errors.
    """
    try:
        redis_client = aioredis.from_url(redis_url)
        pubsub = redis_client.pubsub()

        # Subscribe to exact channels
        await pubsub.subscribe(*CHANNELS.keys())

        # Subscribe to pattern channels
        for pattern in PATTERN_CHANNELS:
            await pubsub.psubscribe(pattern)

        logger.info(
            "Redis subscriber started on channels: %s, patterns: %s",
            list(CHANNELS.keys()),
            list(PATTERN_CHANNELS.keys()),
        )

        async for message in pubsub.listen():
            msg_type = message["type"]

            # Handle exact channel messages
            if msg_type == "message":
                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()

                try:
                    data = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError) as e:
                    logger.error("Failed to parse message on channel %s: %s", channel, e)
                    continue

                user_id = data.get("user_id")
                if user_id is None:
                    logger.warning("Message on channel %s missing user_id: %s", channel, data)
                    continue

                handler = CHANNELS.get(channel)
                if handler:
                    await handler(int(user_id), data)

            # Handle pattern channel messages
            elif msg_type == "pmessage":
                pattern = message["pattern"]
                if isinstance(pattern, bytes):
                    pattern = pattern.decode()

                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()

                try:
                    data = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError) as e:
                    logger.error(
                        "Failed to parse pattern message on channel %s: %s", channel, e
                    )
                    continue

                # Extract user_id from channel name or payload
                user_id = data.get("user_id")
                if user_id is None:
                    # Try extracting from channel name (e.g., "notifications:42")
                    parts = channel.rsplit(":", 1)
                    if len(parts) == 2:
                        try:
                            user_id = int(parts[1])
                        except (ValueError, TypeError):
                            pass

                if user_id is None:
                    logger.warning(
                        "Pattern message on channel %s missing user_id: %s",
                        channel,
                        data,
                    )
                    continue

                handler = PATTERN_CHANNELS.get(pattern)
                if handler:
                    await handler(int(user_id), data)

    except Exception as e:
        logger.error("Redis subscriber error: %s", e)
        raise
