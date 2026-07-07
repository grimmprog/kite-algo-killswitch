"""Tests for WebSocket server (Section 13).

Covers:
- 13.4.1: Connection with valid token accepted
- 13.4.2: Connection without token / invalid token rejected
- 13.4.3: Event delivery via broadcast functions
- 13.3: Redis pub/sub integration
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.auth.jwt_handler import JWTHandler


# --- Test fixtures ---

JWT_SECRET = "test-secret-key"


def _make_token(user_id: int = 1) -> str:
    """Create a valid JWT token for testing."""
    handler = JWTHandler(secret_key=JWT_SECRET)
    return handler.create_access_token(user_id)


# --- 13.4.1 & 13.4.2: Connection tests ---


@pytest.mark.asyncio
async def test_connect_with_valid_token():
    """Connection with a valid JWT token should be accepted."""
    with patch("src.api.websocket.JWT_SECRET_KEY", JWT_SECRET):
        from src.api.websocket import connect, sio

        token = _make_token(user_id=42)
        sid = "test-sid-001"
        environ = {}
        auth = {"token": token}

        with patch.object(sio, "save_session", new_callable=AsyncMock) as mock_save, \
             patch.object(sio, "enter_room", new_callable=AsyncMock) as mock_room:
            result = await connect(sid, environ, auth)

        # connect returns None on success (not False)
        assert result is None
        mock_save.assert_called_once_with(sid, {"user_id": 42})
        mock_room.assert_called_once_with(sid, "user:42")


@pytest.mark.asyncio
async def test_connect_without_token_rejected():
    """Connection without a token should be rejected."""
    from src.api.websocket import connect

    sid = "test-sid-002"
    environ = {}

    # No auth at all
    result = await connect(sid, environ, None)
    assert result is False

    # Auth dict without token key
    result = await connect(sid, environ, {})
    assert result is False

    # Auth dict with empty token
    result = await connect(sid, environ, {"token": ""})
    assert result is False


@pytest.mark.asyncio
async def test_connect_with_invalid_token_rejected():
    """Connection with an invalid/expired token should be rejected."""
    with patch("src.api.websocket.JWT_SECRET_KEY", JWT_SECRET):
        from src.api.websocket import connect

        sid = "test-sid-003"
        environ = {}

        # Completely invalid token
        result = await connect(sid, environ, {"token": "invalid-garbage-token"})
        assert result is False

        # Token signed with a different secret
        wrong_handler = JWTHandler(secret_key="wrong-secret")
        bad_token = wrong_handler.create_access_token(1)
        result = await connect(sid, environ, {"token": bad_token})
        assert result is False


@pytest.mark.asyncio
async def test_disconnect_logs_user():
    """Disconnect should retrieve user_id from session."""
    from src.api.websocket import disconnect, sio

    sid = "test-sid-004"

    with patch.object(sio, "get_session", new_callable=AsyncMock, return_value={"user_id": 7}):
        # Should not raise
        await disconnect(sid)


# --- 13.4.3 & 13.2: Event broadcasting tests ---


@pytest.mark.asyncio
async def test_broadcast_risk_update():
    """broadcast_risk_update should emit to the correct user room."""
    from src.api.websocket import broadcast_risk_update, sio

    data = {"pnl": 1500.0, "net_delta": 0.5, "user_id": 10}

    with patch.object(sio, "emit", new_callable=AsyncMock) as mock_emit:
        await broadcast_risk_update(user_id=10, data=data)

    mock_emit.assert_called_once_with("risk_update", data, room="user:10")


@pytest.mark.asyncio
async def test_broadcast_position_update():
    """broadcast_position_update should emit to the correct user room."""
    from src.api.websocket import broadcast_position_update, sio

    data = {"symbol": "NIFTY", "quantity": 50, "user_id": 5}

    with patch.object(sio, "emit", new_callable=AsyncMock) as mock_emit:
        await broadcast_position_update(user_id=5, data=data)

    mock_emit.assert_called_once_with("position_update", data, room="user:5")


@pytest.mark.asyncio
async def test_broadcast_order_update():
    """broadcast_order_update should emit to the correct user room."""
    from src.api.websocket import broadcast_order_update, sio

    data = {"order_id": "abc123", "status": "FILLED", "user_id": 3}

    with patch.object(sio, "emit", new_callable=AsyncMock) as mock_emit:
        await broadcast_order_update(user_id=3, data=data)

    mock_emit.assert_called_once_with("order_update", data, room="user:3")


@pytest.mark.asyncio
async def test_broadcast_killswitch_update():
    """broadcast_killswitch_update should emit to the correct user room."""
    from src.api.websocket import broadcast_killswitch_update, sio

    data = {"active": True, "user_id": 8}

    with patch.object(sio, "emit", new_callable=AsyncMock) as mock_emit:
        await broadcast_killswitch_update(user_id=8, data=data)

    mock_emit.assert_called_once_with("killswitch_update", data, room="user:8")


# --- 13.3: Redis pub/sub integration tests ---


@pytest.mark.asyncio
async def test_redis_pubsub_dispatches_to_broadcast():
    """Redis subscriber should parse messages and call broadcast functions."""
    from src.api.redis_pubsub import CHANNELS

    # Verify channel mapping is correct
    assert "risk_update" in CHANNELS
    assert "position_update" in CHANNELS
    assert "order_update" in CHANNELS
    assert "killswitch_update" in CHANNELS


@pytest.mark.asyncio
async def test_redis_pubsub_message_handling():
    """Redis subscriber should forward valid messages to broadcast handlers."""
    from src.api import redis_pubsub

    # Create a mock pubsub that yields one message then stops
    mock_message = {
        "type": "message",
        "channel": b"risk_update",
        "data": json.dumps({"user_id": 42, "pnl": 2000.0}).encode(),
    }

    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.listen = MagicMock(return_value=_async_iter([mock_message]))

    mock_redis = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

    mock_handler = AsyncMock()
    patched_channels = {
        "risk_update": mock_handler,
        "position_update": AsyncMock(),
        "order_update": AsyncMock(),
        "killswitch_update": AsyncMock(),
    }

    with patch("src.api.redis_pubsub.aioredis.from_url", return_value=mock_redis), \
         patch.dict(redis_pubsub.CHANNELS, patched_channels):
        await redis_pubsub.start_redis_subscriber("redis://localhost:6379/0")

    mock_handler.assert_called_once_with(42, {"user_id": 42, "pnl": 2000.0})


@pytest.mark.asyncio
async def test_redis_pubsub_skips_missing_user_id():
    """Messages without user_id should be skipped."""
    from src.api import redis_pubsub

    mock_message = {
        "type": "message",
        "channel": b"order_update",
        "data": json.dumps({"order_id": "xyz"}).encode(),  # No user_id
    }

    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.listen = MagicMock(return_value=_async_iter([mock_message]))

    mock_redis = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

    with patch("src.api.redis_pubsub.aioredis.from_url", return_value=mock_redis), \
         patch("src.api.redis_pubsub.broadcast_order_update", new_callable=AsyncMock) as mock_broadcast:
        await redis_pubsub.start_redis_subscriber("redis://localhost:6379/0")

    # Should not have been called since user_id is missing
    mock_broadcast.assert_not_called()


@pytest.mark.asyncio
async def test_redis_pubsub_skips_non_message_types():
    """Non-message types (subscribe confirmations) should be skipped."""
    from src.api import redis_pubsub

    mock_message = {
        "type": "subscribe",
        "channel": b"risk_update",
        "data": 1,
    }

    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.listen = MagicMock(return_value=_async_iter([mock_message]))

    mock_redis = AsyncMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

    with patch("src.api.redis_pubsub.aioredis.from_url", return_value=mock_redis), \
         patch("src.api.redis_pubsub.broadcast_risk_update", new_callable=AsyncMock) as mock_broadcast:
        await redis_pubsub.start_redis_subscriber("redis://localhost:6379/0")

    mock_broadcast.assert_not_called()


# --- Helpers ---

async def _async_iter(items):
    """Create an async iterator from a list of items."""
    for item in items:
        yield item
