"""WebSocket server using Socket.IO for real-time event delivery.

Provides:
- JWT-authenticated WebSocket connections
- User-specific rooms for targeted broadcasts
- Event broadcasting functions for risk, position, order, and kill switch updates
- Scanner signal events (signal_detected, signal_expired, consolidation_update)
- Position monitor events (position_monitor_update, exit_condition_update, auto_exit_triggered)
- Notification events (notification)
- Monitor events (monitor_status, threshold_warning)
- AI events (ai_analysis_result, ai_risk_warning, ai_market_update)
- Price stream events (signal_price_update)

Requirements covered:
- 13.1.1: Configure Socket.IO with ASGI async mode
- 13.1.2: Authenticate connections via JWT token
- 13.1.3: Handle connect/disconnect lifecycle
- 13.2: Event broadcasting to specific users
- 2.4: Real-time consolidation candle updates
- 4.7: Real-time price updates for pending signals
- 7.2: Position monitor price updates every 2s
- 8.5: Exit condition evaluations in real time
- 10.4: Threshold proximity warnings
- 11.2-11.5: Notification push for signals, trades, killswitch, warnings
- 18.1: AI signal quality analysis result delivery
- 21.4: AI exit recommendation alerts
- 22.4: AI market narrative push on significant events
"""

import os
import logging
import socketio

from src.auth.jwt_handler import JWTHandler

logger = logging.getLogger(__name__)

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-key")

# --- 13.1.1: Configure Socket.IO server (async mode for FastAPI) ---
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
)

# Wrap as ASGI app for mounting in FastAPI
socket_app = socketio.ASGIApp(sio)


# --- 13.1.2 & 13.1.3: Authentication and connection handling ---

@sio.event
async def connect(sid, environ, auth):
    """Handle WebSocket connection with JWT authentication.

    Authenticates the connection using a JWT token provided in the auth dict.
    On success, stores user_id in session and joins a user-specific room.
    Returns False to reject unauthenticated connections.

    Args:
        sid: Socket.IO session ID.
        environ: ASGI environ dict.
        auth: Authentication dict from client (expects {"token": "..."}).
    """
    token = auth.get("token") if auth else None
    if not token:
        logger.warning("WebSocket connection rejected: no token provided")
        return False  # Reject connection

    try:
        handler = JWTHandler(secret_key=JWT_SECRET_KEY)
        payload = handler.verify_token(token)
        user_id = int(payload["sub"])
    except Exception as e:
        logger.warning("WebSocket connection rejected: invalid token: %s", e)
        return False  # Reject connection

    # Store user_id in session for later use
    await sio.save_session(sid, {"user_id": user_id})
    # Join user-specific room for targeted broadcasts
    await sio.enter_room(sid, f"user:{user_id}")
    logger.info("WebSocket connected: sid=%s, user_id=%d", sid, user_id)


@sio.event
async def disconnect(sid):
    """Handle WebSocket disconnection.

    Logs the disconnection with user context from the session.

    Args:
        sid: Socket.IO session ID.
    """
    session = await sio.get_session(sid)
    user_id = session.get("user_id", "unknown")
    logger.info("WebSocket disconnected: sid=%s, user_id=%s", sid, user_id)


# --- 13.2: Event broadcasting functions ---

async def broadcast_risk_update(user_id: int, data: dict):
    """Broadcast risk metrics update to a specific user.

    Args:
        user_id: Target user ID.
        data: Risk metrics payload (pnl, greeks, margin, etc.).
    """
    await sio.emit("risk_update", data, room=f"user:{user_id}")


async def broadcast_position_update(user_id: int, data: dict):
    """Broadcast position change to a specific user.

    Args:
        user_id: Target user ID.
        data: Position update payload.
    """
    await sio.emit("position_update", data, room=f"user:{user_id}")


async def broadcast_order_update(user_id: int, data: dict):
    """Broadcast order status change to a specific user.

    Args:
        user_id: Target user ID.
        data: Order update payload.
    """
    await sio.emit("order_update", data, room=f"user:{user_id}")


async def broadcast_killswitch_update(user_id: int, data: dict):
    """Broadcast kill switch state change to a specific user.

    Args:
        user_id: Target user ID.
        data: Kill switch update payload (active/inactive state).
    """
    await sio.emit("killswitch_update", data, room=f"user:{user_id}")


# --- Scanner events (Requirements 2.4, 4.7, 11.2) ---

async def broadcast_signal_detected(user_id: int, data: dict):
    """Push new scanner signal to user.

    Emitted when the scanner worker detects a signal meeting the confidence
    threshold. Payload matches TradingSignal schema (symbol, confidence_score,
    entry_price, stop_loss, target_price, max_loss, countdown_seconds, etc.).

    Args:
        user_id: Target user ID.
        data: TradingSignal payload dict.
    """
    await sio.emit("signal_detected", data, room=f"user:{user_id}")


async def broadcast_signal_expired(user_id: int, data: dict):
    """Push signal expiry notification.

    Emitted when a pending signal's countdown timer expires without
    trader action. Payload includes signal_id and expiry timestamp.

    Args:
        user_id: Target user ID.
        data: Signal expiry payload (signal_id, expired_at).
    """
    await sio.emit("signal_expired", data, room=f"user:{user_id}")


async def broadcast_consolidation_update(user_id: int, data: dict):
    """Push consolidation pattern update at 3-minute intervals.

    Emitted by the consolidation scanner worker with updated pattern data
    including range_high, range_low, avg_price, candle_count, duration,
    and breakout status.

    Args:
        user_id: Target user ID.
        data: ConsolidationPattern payload dict.
    """
    await sio.emit("consolidation_update", data, room=f"user:{user_id}")


# --- Position monitor events (Requirements 7.2, 8.5) ---

async def broadcast_position_monitor_update(user_id: int, data: dict):
    """Push SL/Target/Trailing status per position (every 2 seconds).

    Emitted by the position monitor worker with live price data and
    computed distances to stop-loss, target, and trailing stop levels.

    Args:
        user_id: Target user ID.
        data: MonitoredPosition payload dict (position_id, current_price,
              stop_loss, target, trailing_stop_level, unrealized_pnl,
              distance_to_sl_pct, distance_to_target_pct, status).
    """
    await sio.emit("position_monitor_update", data, room=f"user:{user_id}")


async def broadcast_exit_condition_update(user_id: int, data: dict):
    """Push exit condition evaluation changes.

    Emitted when exit conditions (EMA cross, VWAP touch, consecutive
    green candles, time-based) are re-evaluated for a position.

    Args:
        user_id: Target user ID.
        data: Exit conditions payload (position_id, conditions list with
              name, is_met, details).
    """
    await sio.emit("exit_condition_update", data, room=f"user:{user_id}")


async def broadcast_auto_exit_triggered(user_id: int, data: dict):
    """Push auto-exit event (SL hit, target hit, trailing stop hit).

    Emitted when the position monitor triggers an automatic exit order
    for a position due to SL/Target/Trailing stop being hit.

    Args:
        user_id: Target user ID.
        data: Auto-exit payload (position_id, symbol, exit_reason,
              exit_price, pnl).
    """
    await sio.emit("auto_exit_triggered", data, room=f"user:{user_id}")


# --- Notification events (Requirements 11.2-11.5) ---

async def broadcast_notification(user_id: int, data: dict):
    """Push notification to user's feed.

    Covers all notification types: signal detected, trade executed,
    kill switch triggered, threshold warning, AI alerts, and system events.

    Args:
        user_id: Target user ID.
        data: Notification payload (id, severity, title, message,
              category, timestamp, metadata).
    """
    await sio.emit("notification", data, room=f"user:{user_id}")


# --- Monitor events (Requirements 10.4, 10.5) ---

async def broadcast_monitor_status(user_id: int, data: dict):
    """Push current P&L and distance to kill switch threshold.

    Emitted periodically by the auto-monitor worker while monitoring
    is active, showing the user their live P&L position relative to
    configured thresholds.

    Args:
        user_id: Target user ID.
        data: Monitor status payload (current_pnl, nearest_threshold,
              distance_to_threshold, monitoring_active).
    """
    await sio.emit("monitor_status", data, room=f"user:{user_id}")


async def broadcast_threshold_warning(user_id: int, data: dict):
    """Push warning when P&L is within 10% of kill switch threshold.

    Emitted when the auto-monitor detects that the user's P&L has
    approached within 10% of any configured kill switch threshold.

    Args:
        user_id: Target user ID.
        data: Threshold warning payload (threshold_type, threshold_value,
              current_value, distance_pct, severity).
    """
    await sio.emit("threshold_warning", data, room=f"user:{user_id}")


# --- AI events (Requirements 18.1, 21.4, 22.4) ---

async def broadcast_ai_analysis_result(user_id: int, data: dict):
    """Push AI analysis result (signal quality, entry suggestion, exit, etc.).

    Emitted when an AI analysis task completes (signal quality rating,
    consolidation analysis, exit recommendation). Payload varies by
    analysis type.

    Args:
        user_id: Target user ID.
        data: AI analysis payload (analysis_type, result dict).
    """
    await sio.emit("ai_analysis_result", data, room=f"user:{user_id}")


async def broadcast_ai_risk_warning(user_id: int, data: dict):
    """Push proactive AI risk warning.

    Emitted when the AI detects behavioral anomalies (revenge trading,
    consecutive losses) or adverse market conditions requiring trader
    attention.

    Args:
        user_id: Target user ID.
        data: AI risk warning payload (severity, message, category,
              requires_acknowledgment).
    """
    await sio.emit("ai_risk_warning", data, room=f"user:{user_id}")


async def broadcast_ai_market_update(user_id: int, data: dict):
    """Push AI market narrative update at scheduled intervals.

    Emitted at market open (9:15), mid-morning (10:30), lunch (12:30),
    and afternoon (14:00), or on significant intraday events (sharp
    move >1% in 15min, VIX spike >10%).

    Args:
        user_id: Target user ID.
        data: AI market narrative payload (session_type, key_points,
              bias, expected_range, key_levels).
    """
    await sio.emit("ai_market_update", data, room=f"user:{user_id}")


# --- Price stream for signal approval panel (Requirement 4.7) ---

async def broadcast_signal_price_update(user_id: int, data: dict):
    """Push real-time price for pending signal's symbol.

    Emitted while a signal is pending approval, delivering live price
    data so the trader can see current price movement relative to the
    suggested entry.

    Args:
        user_id: Target user ID.
        data: Price update payload (signal_id, symbol, current_price,
              change_from_entry_pct, timestamp).
    """
    await sio.emit("signal_price_update", data, room=f"user:{user_id}")
