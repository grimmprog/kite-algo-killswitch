"""AI Analysis Worker — Celery tasks for asynchronous AI-powered trade analysis.

Provides background tasks for AI signal analysis, exit recommendations,
market narrative generation, and risk anomaly detection. Results are
published via Redis PubSub for WebSocket delivery to the frontend.

Requirements covered:
- 18.6: AI signal analysis completes within 5 seconds
- 21.1: AI exit evaluation runs on 30-second cycles
- 22.2: AI market narrative updates at scheduled intervals
- 24.1: AI risk anomaly detection for behavioral patterns
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict

from celery.exceptions import SoftTimeLimitExceeded

from src.cache.redis_client import get_redis_client
from src.services.ai_trading_service import AIProvider, AITradingService
from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_ai_service() -> AITradingService:
    """Create an AITradingService instance from environment configuration.

    Reads AI provider and API key from environment variables.

    Returns:
        Configured AITradingService instance.

    Raises:
        RuntimeError: If no AI API key is configured.
    """
    provider_str = os.environ.get("AI_PROVIDER", "gemini")
    try:
        provider = AIProvider(provider_str)
    except ValueError:
        provider = AIProvider.GEMINI

    api_key = os.environ.get(f"AI_{provider_str.upper()}_API_KEY", "")
    if not api_key:
        api_key = os.environ.get("AI_API_KEY", "")

    if not api_key:
        raise RuntimeError("No AI API key configured in environment")

    return AITradingService(provider=provider, api_key=api_key)


def _is_ai_feature_enabled(user_id: int, feature_name: str) -> bool:
    """Check if a specific AI feature is enabled for the user via Redis cache.

    Reads AI settings from Redis (populated by settings service on update).
    If cache is unavailable, defaults to enabled (fail-open for AI features).

    Feature names map to AISettings fields:
    - "signal_analysis" → signal_analysis_enabled
    - "entry_suggestions" → entry_suggestions_enabled
    - "exit_recommendations" → exit_recommendations_enabled
    - "market_narrative" → market_narrative_enabled
    - "trade_review" → trade_review_enabled
    - "risk_warnings" → risk_warnings_enabled

    Args:
        user_id: The user's database ID.
        feature_name: The AI feature to check.

    Returns:
        True if enabled (or cache unavailable), False if explicitly disabled.
    """
    from src.services.settings_service import SettingsService

    cached = SettingsService.get_cached_ai_settings(user_id)
    if cached is None:
        # Cache miss — fail open (assume enabled)
        return True

    key = f"{feature_name}_enabled"
    return cached.get(key, True)


def _publish_result(channel: str, data: Dict[str, Any]) -> bool:
    """Publish a result to a Redis PubSub channel for WebSocket relay.

    Args:
        channel: The Redis PubSub channel name (e.g., "ai:signal_analysis:123").
        data: The result data to publish as JSON.

    Returns:
        True if the publish succeeded, False otherwise.
    """
    try:
        redis_client = get_redis_client()
        payload = json.dumps(data, default=str)
        redis_client.client.publish(channel, payload)
        logger.debug("Published result to channel '%s'", channel)
        return True
    except Exception as e:
        logger.error(
            "Failed to publish to channel '%s': %s: %s",
            channel,
            type(e).__name__,
            str(e),
        )
        return False


def _unavailable_result(task_type: str, reason: str = "AI unavailable") -> Dict[str, Any]:
    """Build a graceful degradation response when AI is unavailable.

    Args:
        task_type: The type of AI task that failed.
        reason: Human-readable reason for unavailability.

    Returns:
        Dict with error status and metadata.
    """
    return {
        "status": "unavailable",
        "task_type": task_type,
        "message": reason,
        "timestamp": datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# Task 1: Analyze Signal Quality
# ---------------------------------------------------------------------------


@celery_app.task(
    name="src.workers.ai_worker.analyze_signal_quality",
    soft_time_limit=5,
    time_limit=10,
    acks_late=True,
    max_retries=0,
)
def analyze_signal_quality(user_id: int, signal_context: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze signal quality using AI with a 5-second timeout.

    Calls AITradingService.analyze_signal() and publishes the result
    to Redis PubSub channel "ai:signal_analysis:{user_id}" for
    WebSocket delivery.

    The task has a soft_time_limit of 5 seconds (Requirement 18.6).
    If the analysis exceeds 5 seconds, it gracefully returns an
    "AI unavailable" status.

    Checks the user's AI settings cache to ensure signal analysis is enabled
    before proceeding. If disabled, returns a "feature disabled" response.

    Args:
        user_id: The user who requested the analysis.
        signal_context: Signal data (symbol, timeframe, indicators, etc.).

    Returns:
        Dict with the analysis result or degradation response.

    Requirements: 18.6
    """
    channel = f"ai:signal_analysis:{user_id}"

    # Check if signal analysis is enabled for this user (Requirement 17.2)
    if not _is_ai_feature_enabled(user_id, "signal_analysis"):
        result = _unavailable_result(
            "signal_analysis", "Signal analysis is disabled in settings"
        )
        result["user_id"] = user_id
        _publish_result(channel, result)
        return result

    try:
        ai_service = _get_ai_service()
    except RuntimeError as e:
        result = _unavailable_result("signal_analysis", str(e))
        _publish_result(channel, result)
        return result

    try:
        analysis = ai_service.analyze_signal(signal_context)

        # Build the result payload
        result = {
            "status": "success",
            "task_type": "signal_analysis",
            "user_id": user_id,
            "data": analysis,
            "timestamp": datetime.now().isoformat(),
        }

        # Check if the AI service itself returned a degraded response
        if isinstance(analysis, dict) and analysis.get("error"):
            result["status"] = "unavailable"
            result["message"] = analysis.get("message", "AI analysis unavailable")

        _publish_result(channel, result)
        return result

    except SoftTimeLimitExceeded:
        logger.warning(
            "AI signal analysis timed out (5s) for user %d", user_id
        )
        result = _unavailable_result(
            "signal_analysis",
            "AI signal analysis timed out — analysis took longer than 5 seconds",
        )
        result["user_id"] = user_id
        _publish_result(channel, result)
        return result

    except Exception as e:
        logger.error(
            "AI signal analysis failed for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        result = _unavailable_result("signal_analysis", "AI analysis unavailable")
        result["user_id"] = user_id
        _publish_result(channel, result)
        return result


# ---------------------------------------------------------------------------
# Task 2: Evaluate Exit (AI Exit Advisor)
# ---------------------------------------------------------------------------


@celery_app.task(
    name="src.workers.ai_worker.schedule_exit_evaluations",
    soft_time_limit=25,
    time_limit=30,
    acks_late=True,
    max_retries=0,
)
def schedule_exit_evaluations() -> Dict[str, Any]:
    """Schedule exit evaluations for all open positions across all users.

    This task runs every 30 seconds (Requirement 21.1) via Celery Beat.
    It fetches all users with open positions from Redis and dispatches
    individual evaluate_exit_ai tasks for each position.

    This is a scheduler task — it does NOT evaluate positions itself.
    It dispatches evaluate_exit_ai for each open position to distribute
    the work across workers.

    The non-execution guarantee is maintained: this task only schedules
    evaluation, never places orders (Requirement 21.6).

    Returns:
        Dict with scheduling status and number of evaluations dispatched.
    """
    try:
        redis_client = get_redis_client()

        # Get all users with active position monitoring
        # Positions are cached by position_monitor_worker with keys:
        # position_monitor:{user_id}:{position_id}
        pattern = "position_monitor:*"
        user_keys = redis_client.client.keys(pattern)

        if not user_keys:
            return {
                "status": "success",
                "evaluations_dispatched": 0,
                "message": "No active positions to evaluate",
                "timestamp": datetime.now().isoformat(),
            }

        evaluations_dispatched = 0

        # Group positions by user_id
        # Key format: position_monitor:{user_id}:{position_id}
        user_positions: Dict[int, list] = {}

        for key in user_keys:
            try:
                key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                parts = key_str.split(":")
                # Expected format: position_monitor:{user_id}:{position_id}
                if len(parts) != 3:
                    continue

                user_id = int(parts[1])
                position_json = redis_client.client.get(key_str)
                if not position_json:
                    continue

                position = json.loads(
                    position_json.decode("utf-8")
                    if isinstance(position_json, bytes)
                    else position_json
                )

                if isinstance(position, dict) and position.get("status") == "active":
                    if user_id not in user_positions:
                        user_positions[user_id] = []
                    user_positions[user_id].append(position)

            except (ValueError, json.JSONDecodeError) as e:
                logger.warning(
                    "Failed to parse position data for key %s: %s",
                    key,
                    str(e),
                )
                continue

        # Dispatch evaluate_exit_ai for each active position
        for user_id, positions in user_positions.items():
            # Get latest market data from Redis cache
            market_data_json = redis_client.client.get(f"market_data:{user_id}")
            market_data = {}
            if market_data_json:
                market_data = json.loads(
                    market_data_json.decode("utf-8")
                    if isinstance(market_data_json, bytes)
                    else market_data_json
                )

            for position in positions:
                evaluate_exit_ai.delay(user_id, position, market_data)
                evaluations_dispatched += 1

        return {
            "status": "success",
            "evaluations_dispatched": evaluations_dispatched,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(
            "Failed to schedule exit evaluations: %s: %s",
            type(e).__name__,
            str(e),
        )
        return {
            "status": "error",
            "evaluations_dispatched": 0,
            "message": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@celery_app.task(
    name="src.workers.ai_worker.evaluate_exit_ai",
    soft_time_limit=10,
    time_limit=15,
    acks_late=True,
    max_retries=0,
)
def evaluate_exit_ai(
    user_id: int, position: Dict[str, Any], market_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Evaluate exit recommendation for an open position using AI.

    Calls AITradingService.evaluate_exit() and publishes the result
    to Redis PubSub channel "ai:exit_recommendation:{user_id}" for
    WebSocket delivery.

    This task is ADVISORY ONLY — it never executes exits automatically.
    All exit actions require explicit trader confirmation.

    Checks the user's AI settings cache to ensure exit recommendations
    are enabled before proceeding.

    Args:
        user_id: The user who owns the position.
        position: Position data (entry_price, current_price, symbol, etc.).
        market_data: Current market conditions (MACD, momentum, volume, etc.).

    Returns:
        Dict with the exit recommendation or degradation response.

    Requirements: 21.1
    """
    channel = f"ai:exit_recommendation:{user_id}"

    # Check if exit recommendations are enabled for this user
    if not _is_ai_feature_enabled(user_id, "exit_recommendations"):
        result = _unavailable_result(
            "exit_recommendation", "Exit recommendations are disabled in settings"
        )
        result["user_id"] = user_id
        result["position_id"] = position.get("position_id")
        _publish_result(channel, result)
        return result

    try:
        ai_service = _get_ai_service()
    except RuntimeError as e:
        result = _unavailable_result("exit_recommendation", str(e))
        _publish_result(channel, result)
        return result

    try:
        recommendation = ai_service.evaluate_exit(position, market_data)

        result = {
            "status": "success",
            "task_type": "exit_recommendation",
            "user_id": user_id,
            "position_id": position.get("position_id"),
            "data": recommendation,
            "timestamp": datetime.now().isoformat(),
        }

        # Check if the AI service returned a degraded response
        if isinstance(recommendation, dict) and recommendation.get("error"):
            result["status"] = "unavailable"
            result["message"] = recommendation.get("message", "AI analysis unavailable")

        _publish_result(channel, result)
        return result

    except SoftTimeLimitExceeded:
        logger.warning(
            "AI exit evaluation timed out for user %d, position %s",
            user_id,
            position.get("position_id"),
        )
        result = _unavailable_result(
            "exit_recommendation",
            "AI exit evaluation timed out",
        )
        result["user_id"] = user_id
        result["position_id"] = position.get("position_id")
        _publish_result(channel, result)
        return result

    except Exception as e:
        logger.error(
            "AI exit evaluation failed for user %d, position %s: %s: %s",
            user_id,
            position.get("position_id"),
            type(e).__name__,
            str(e),
        )
        result = _unavailable_result("exit_recommendation", "AI analysis unavailable")
        result["user_id"] = user_id
        result["position_id"] = position.get("position_id")
        _publish_result(channel, result)
        return result


# ---------------------------------------------------------------------------
# Task 3: Generate Market Narrative
# ---------------------------------------------------------------------------


@celery_app.task(
    name="src.workers.ai_worker.generate_market_narrative",
    soft_time_limit=15,
    time_limit=20,
    acks_late=True,
    max_retries=1,
)
def generate_market_narrative(
    user_id: int, session_type: str, market_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate AI market narrative for the specified session.

    Calls AITradingService.generate_narrative() and publishes the result
    to Redis PubSub channel "ai:market_narrative:{user_id}" for
    WebSocket delivery. Also caches the narrative in Redis for 15 minutes.

    Checks the user's AI settings cache to ensure market narrative is enabled.

    Session types:
    - "morning_brief": 9:15 IST opening brief
    - "mid_morning": 10:30 IST first hour review
    - "lunch": 12:30 IST mid-day assessment
    - "afternoon": 14:00 IST closing outlook

    Args:
        user_id: The user who requested the narrative.
        session_type: One of "morning_brief", "mid_morning", "lunch", "afternoon".
        market_data: Market data for context (indices, VIX, FII/DII, etc.).

    Returns:
        Dict with the narrative result or degradation response.

    Requirements: 22.2
    """
    channel = f"ai:market_narrative:{user_id}"

    # Check if market narrative is enabled for this user
    if not _is_ai_feature_enabled(user_id, "market_narrative"):
        result = _unavailable_result(
            "market_narrative", "Market narrative is disabled in settings"
        )
        result["user_id"] = user_id
        result["session_type"] = session_type
        _publish_result(channel, result)
        return result

    try:
        ai_service = _get_ai_service()
    except RuntimeError as e:
        result = _unavailable_result("market_narrative", str(e))
        _publish_result(channel, result)
        return result

    try:
        narrative = ai_service.generate_narrative(session_type, market_data)

        result = {
            "status": "success",
            "task_type": "market_narrative",
            "user_id": user_id,
            "session_type": session_type,
            "data": narrative,
            "timestamp": datetime.now().isoformat(),
        }

        # Check if the AI service returned a degraded response
        if isinstance(narrative, dict) and narrative.get("error"):
            result["status"] = "unavailable"
            result["message"] = narrative.get("message", "AI analysis unavailable")
        else:
            # Cache successful narrative for 15 minutes
            try:
                redis_client = get_redis_client()
                cache_key = f"ai:narrative:{session_type}"
                redis_client.setex(cache_key, 900, json.dumps(narrative, default=str))
            except Exception as cache_err:
                logger.warning(
                    "Failed to cache narrative: %s", str(cache_err)
                )

        _publish_result(channel, result)
        return result

    except SoftTimeLimitExceeded:
        logger.warning(
            "AI market narrative timed out for user %d, session %s",
            user_id,
            session_type,
        )
        result = _unavailable_result(
            "market_narrative",
            "AI market narrative generation timed out",
        )
        result["user_id"] = user_id
        result["session_type"] = session_type
        _publish_result(channel, result)
        return result

    except Exception as e:
        logger.error(
            "AI market narrative failed for user %d, session %s: %s: %s",
            user_id,
            session_type,
            type(e).__name__,
            str(e),
        )
        result = _unavailable_result("market_narrative", "AI analysis unavailable")
        result["user_id"] = user_id
        result["session_type"] = session_type
        _publish_result(channel, result)
        return result


# ---------------------------------------------------------------------------
# Task 4: Detect Risk Anomalies
# ---------------------------------------------------------------------------


@celery_app.task(
    name="src.workers.ai_worker.detect_risk_anomalies",
    soft_time_limit=10,
    time_limit=15,
    acks_late=True,
    max_retries=0,
)
def detect_risk_anomalies(
    user_id: int, user_state: Dict[str, Any], market_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Detect behavioral anomalies and market risks using AI.

    Calls AITradingService.detect_risk_anomalies() and publishes the
    result to Redis PubSub channel "ai:risk_warnings:{user_id}" for
    WebSocket delivery.

    Checks the user's AI settings cache to ensure risk warnings are enabled.

    Detects patterns such as:
    - 3+ consecutive losses → break suggestion
    - New trade within 5 min of loss on same/correlated symbol → revenge trading
    - Rule violations requiring acknowledgment

    Args:
        user_id: The user to analyze.
        user_state: User's recent trading state (trades, losses, timing, etc.).
        market_data: Current market conditions.

    Returns:
        Dict with risk warnings or degradation response.

    Requirements: 24.1
    """
    channel = f"ai:risk_warnings:{user_id}"

    # Check if risk warnings are enabled for this user
    if not _is_ai_feature_enabled(user_id, "risk_warnings"):
        result = _unavailable_result(
            "risk_anomaly_detection", "Risk warnings are disabled in settings"
        )
        result["user_id"] = user_id
        _publish_result(channel, result)
        return result

    try:
        ai_service = _get_ai_service()
    except RuntimeError as e:
        result = _unavailable_result("risk_anomaly_detection", str(e))
        _publish_result(channel, result)
        return result

    try:
        warnings = ai_service.detect_risk_anomalies(user_state, market_data)

        result = {
            "status": "success",
            "task_type": "risk_anomaly_detection",
            "user_id": user_id,
            "data": warnings,
            "timestamp": datetime.now().isoformat(),
        }

        # Check if the AI service returned a degraded response
        if isinstance(warnings, dict) and warnings.get("error"):
            result["status"] = "unavailable"
            result["message"] = warnings.get("message", "AI analysis unavailable")

        _publish_result(channel, result)
        return result

    except SoftTimeLimitExceeded:
        logger.warning(
            "AI risk anomaly detection timed out for user %d", user_id
        )
        result = _unavailable_result(
            "risk_anomaly_detection",
            "AI risk analysis timed out",
        )
        result["user_id"] = user_id
        _publish_result(channel, result)
        return result

    except Exception as e:
        logger.error(
            "AI risk anomaly detection failed for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        result = _unavailable_result("risk_anomaly_detection", "AI analysis unavailable")
        result["user_id"] = user_id
        _publish_result(channel, result)
        return result
