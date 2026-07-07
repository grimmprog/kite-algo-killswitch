"""Settings service for user strategy parameters, kill switch thresholds, segments, and AI config.

Implements Requirements: 5.1-5.7, 6.1-6.6
Settings propagation: 5.2, 6.4 — Changes cache in Redis for worker consumption.
"""

import json
import logging
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.cache.redis_client import RedisClient, get_redis_client
from src.cache.redis_keys import RedisKeys, SettingsTTL
from src.database.models.user_settings import UserSettings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------


class StrategySettings(BaseModel):
    """Strategy configuration returned to/from the frontend."""

    model_config = ConfigDict(from_attributes=True)

    watchlist: List[str]
    trading_start_time: str  # "HH:MM"
    trading_end_time: str  # "HH:MM"
    confidence_threshold: int = Field(ge=50, le=100)
    max_trades_per_day: int = Field(ge=1, le=10)
    max_active_trades: int = Field(ge=1, le=5)
    capital: float = Field(gt=0)
    lot_sizes: dict  # {"NIFTY": 25, "BANKNIFTY": 15, ...}


class KillSwitchThresholds(BaseModel):
    """Kill switch threshold configuration."""

    model_config = ConfigDict(from_attributes=True)

    daily_loss_type: str  # "percentage" or "absolute"
    daily_loss_value: float = Field(gt=0)
    profit_target_type: str  # "percentage" or "absolute"
    profit_target_value: float = Field(gt=0)
    drawdown_type: str  # "percentage" or "absolute"
    drawdown_value: float = Field(gt=0)
    profit_warning_pct: float = Field(gt=0)


class KillSwitchThresholdsResponse(BaseModel):
    """Kill switch thresholds with computed absolute amounts."""

    daily_loss_type: str
    daily_loss_value: float
    daily_loss_amount: float  # computed: capital × percentage / 100
    profit_target_type: str
    profit_target_value: float
    profit_target_amount: float
    drawdown_type: str
    drawdown_value: float
    drawdown_amount: float
    profit_warning_pct: float
    capital: float
    warning: Optional[str] = None  # set when daily_loss > 25% of capital


class SegmentStatus(BaseModel):
    """Segment activation status."""

    segment: str  # NSE, BSE, NFO, BFO
    is_active: bool
    deactivated_by_killswitch: bool = False


class AISettings(BaseModel):
    """AI trading assistant configuration."""

    model_config = ConfigDict(from_attributes=True)

    provider: str  # "gemini" or "claude"
    api_key_configured: bool  # Never expose actual key
    signal_analysis_enabled: bool
    entry_suggestions_enabled: bool
    exit_recommendations_enabled: bool
    market_narrative_enabled: bool
    trade_review_enabled: bool
    risk_warnings_enabled: bool


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_time_format(time_str: str) -> bool:
    """Validate HH:MM format and range."""
    if not time_str or len(time_str) != 5 or time_str[2] != ":":
        return False
    try:
        hours, minutes = time_str.split(":")
        h, m = int(hours), int(minutes)
        return 0 <= h <= 23 and 0 <= m <= 59
    except (ValueError, IndexError):
        return False


def _time_before(start: str, end: str) -> bool:
    """Return True if start time is strictly before end time (HH:MM comparison)."""
    return start < end


def _compute_amount(capital: float, threshold_type: str, value: float) -> float:
    """Compute absolute amount from threshold type and value.

    If type is 'percentage', amount = capital × value / 100.
    If type is 'absolute', amount = value.
    """
    if threshold_type == "percentage":
        return capital * value / 100.0
    return value


def _check_daily_loss_warning(
    capital: float, daily_loss_type: str, daily_loss_value: float
) -> Optional[str]:
    """Return warning string if daily loss exceeds 25% of capital.

    Warning triggers when:
    - daily_loss_type == 'percentage' and daily_loss_value > 25
    - daily_loss_type == 'absolute' and daily_loss_value > capital * 0.25
    """
    if daily_loss_type == "percentage" and daily_loss_value > 25:
        return (
            f"Warning: Daily loss threshold ({daily_loss_value}%) exceeds 25% of capital. "
            f"This represents ₹{capital * daily_loss_value / 100:.2f} risk."
        )
    if daily_loss_type == "absolute" and daily_loss_value > capital * 0.25:
        pct = (daily_loss_value / capital) * 100 if capital > 0 else 0
        return (
            f"Warning: Daily loss threshold (₹{daily_loss_value:.2f}) exceeds 25% of capital "
            f"(₹{capital * 0.25:.2f}). This is {pct:.1f}% of your capital."
        )
    return None


# ---------------------------------------------------------------------------
# SettingsService
# ---------------------------------------------------------------------------


class SettingsService:
    """Manages all user-configurable settings.

    Uses synchronous SQLAlchemy Session for database operations.
    """

    # ------------------------------------------------------------------
    # Strategy Settings
    # ------------------------------------------------------------------

    def get_strategy_settings(self, db: Session, user_id: int) -> StrategySettings:
        """Load UserSettings from DB and return as StrategySettings pydantic model.

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.

        Returns:
            StrategySettings populated from the database.

        Raises:
            ValueError: If no settings found for user.
        """
        settings = self._get_user_settings(db, user_id)
        return StrategySettings(
            watchlist=settings.watchlist or [],
            trading_start_time=settings.trading_start_time,
            trading_end_time=settings.trading_end_time,
            confidence_threshold=settings.confidence_threshold,
            max_trades_per_day=settings.max_trades_per_day,
            max_active_trades=settings.max_active_trades,
            capital=settings.capital,
            lot_sizes=settings.lot_sizes or {},
        )

    def update_strategy_settings(
        self, db: Session, user_id: int, settings: StrategySettings
    ) -> StrategySettings:
        """Validate and persist updated strategy settings.

        Also caches the settings and watchlist in Redis so workers (scanner,
        position monitor) pick up changes on their next cycle without hitting DB.

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.
            settings: New strategy settings to persist.

        Returns:
            The updated StrategySettings.

        Raises:
            ValueError: If validation fails (time format, time ordering, bounds).
        """
        # Validate time format
        if not _validate_time_format(settings.trading_start_time):
            raise ValueError(
                f"Invalid trading_start_time format: '{settings.trading_start_time}'. "
                f"Expected HH:MM (e.g. '09:15')."
            )
        if not _validate_time_format(settings.trading_end_time):
            raise ValueError(
                f"Invalid trading_end_time format: '{settings.trading_end_time}'. "
                f"Expected HH:MM (e.g. '15:30')."
            )

        # Validate start < end
        if not _time_before(settings.trading_start_time, settings.trading_end_time):
            raise ValueError(
                f"trading_start_time ({settings.trading_start_time}) must be before "
                f"trading_end_time ({settings.trading_end_time})."
            )

        # Pydantic Field constraints already validate:
        # confidence_threshold: 50-100
        # max_trades_per_day: 1-10
        # capital: > 0
        # But we double-check for safety when called directly
        if settings.confidence_threshold < 50 or settings.confidence_threshold > 100:
            raise ValueError("Confidence threshold must be between 50 and 100")
        if settings.max_trades_per_day < 1 or settings.max_trades_per_day > 10:
            raise ValueError("Max trades per day must be between 1 and 10")
        if settings.capital <= 0:
            raise ValueError("Capital must be positive")

        user_settings = self._get_user_settings(db, user_id)

        user_settings.watchlist = settings.watchlist
        user_settings.trading_start_time = settings.trading_start_time
        user_settings.trading_end_time = settings.trading_end_time
        user_settings.confidence_threshold = settings.confidence_threshold
        user_settings.max_trades_per_day = settings.max_trades_per_day
        user_settings.max_active_trades = settings.max_active_trades
        user_settings.capital = settings.capital
        user_settings.lot_sizes = settings.lot_sizes

        db.commit()
        db.refresh(user_settings)

        result = self.get_strategy_settings(db, user_id)

        # Cache in Redis for workers (Requirements 5.2)
        self._cache_strategy_settings(user_id, result)

        return result

    # ------------------------------------------------------------------
    # Kill Switch Thresholds
    # ------------------------------------------------------------------

    def get_killswitch_thresholds(
        self, db: Session, user_id: int
    ) -> KillSwitchThresholdsResponse:
        """Return kill switch thresholds with computed absolute amounts.

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.

        Returns:
            KillSwitchThresholdsResponse with computed amounts and optional warning.
        """
        settings = self._get_user_settings(db, user_id)

        daily_loss_amount = _compute_amount(
            settings.capital, settings.daily_loss_type, settings.daily_loss_value
        )
        profit_target_amount = _compute_amount(
            settings.capital, settings.profit_target_type, settings.profit_target_value
        )
        drawdown_amount = _compute_amount(
            settings.capital, settings.drawdown_type, settings.drawdown_value
        )

        warning = _check_daily_loss_warning(
            settings.capital, settings.daily_loss_type, settings.daily_loss_value
        )

        return KillSwitchThresholdsResponse(
            daily_loss_type=settings.daily_loss_type,
            daily_loss_value=settings.daily_loss_value,
            daily_loss_amount=daily_loss_amount,
            profit_target_type=settings.profit_target_type,
            profit_target_value=settings.profit_target_value,
            profit_target_amount=profit_target_amount,
            drawdown_type=settings.drawdown_type,
            drawdown_value=settings.drawdown_value,
            drawdown_amount=drawdown_amount,
            profit_warning_pct=settings.profit_warning_pct,
            capital=settings.capital,
            warning=warning,
        )

    def update_killswitch_thresholds(
        self, db: Session, user_id: int, thresholds: KillSwitchThresholds
    ) -> KillSwitchThresholdsResponse:
        """Validate, persist thresholds, and cache in Redis for immediate worker pickup.

        Kill switch threshold changes apply immediately to the auto-monitor worker
        which reads from Redis cache on each 5-second cycle (Requirement 6.4).

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.
            thresholds: New kill switch thresholds.

        Returns:
            KillSwitchThresholdsResponse with computed amounts and optional warning.

        Raises:
            ValueError: If threshold values are not positive or types are invalid.
        """
        # Validate types
        valid_types = ("percentage", "absolute")
        if thresholds.daily_loss_type not in valid_types:
            raise ValueError(
                f"daily_loss_type must be 'percentage' or 'absolute', "
                f"got '{thresholds.daily_loss_type}'"
            )
        if thresholds.profit_target_type not in valid_types:
            raise ValueError(
                f"profit_target_type must be 'percentage' or 'absolute', "
                f"got '{thresholds.profit_target_type}'"
            )
        if thresholds.drawdown_type not in valid_types:
            raise ValueError(
                f"drawdown_type must be 'percentage' or 'absolute', "
                f"got '{thresholds.drawdown_type}'"
            )

        # Validate values are positive (Pydantic gt=0 handles this, but explicit check)
        if thresholds.daily_loss_value <= 0:
            raise ValueError("daily_loss_value must be positive")
        if thresholds.profit_target_value <= 0:
            raise ValueError("profit_target_value must be positive")
        if thresholds.drawdown_value <= 0:
            raise ValueError("drawdown_value must be positive")
        if thresholds.profit_warning_pct <= 0:
            raise ValueError("profit_warning_pct must be positive")

        user_settings = self._get_user_settings(db, user_id)

        user_settings.daily_loss_type = thresholds.daily_loss_type
        user_settings.daily_loss_value = thresholds.daily_loss_value
        user_settings.profit_target_type = thresholds.profit_target_type
        user_settings.profit_target_value = thresholds.profit_target_value
        user_settings.drawdown_type = thresholds.drawdown_type
        user_settings.drawdown_value = thresholds.drawdown_value
        user_settings.profit_warning_pct = thresholds.profit_warning_pct

        db.commit()
        db.refresh(user_settings)

        result = self.get_killswitch_thresholds(db, user_id)

        # Cache in Redis immediately for auto-monitor worker (Requirement 6.4)
        self._cache_killswitch_thresholds(user_id, result)

        return result

    # ------------------------------------------------------------------
    # Segments
    # ------------------------------------------------------------------

    def get_segments(self, user_id: int) -> List[SegmentStatus]:
        """Return list of all segment statuses with kill switch deactivation info.

        Checks Redis for the kill switch flag and segment deactivation state.
        When the kill switch is active, segments that were deactivated by it
        are marked with deactivated_by_killswitch=True.

        In production, base activation status would come from Zerodha API.

        Args:
            user_id: The user's ID.

        Returns:
            List of SegmentStatus for NSE, BSE, NFO, BFO with kill switch info.
        """
        from src.services.killswitch_integration import get_killswitch_deactivated_segments

        # Check which segments were deactivated by kill switch
        redis_client = get_redis_client()
        killswitch_key = RedisKeys.user_killswitch(user_id)
        killswitch_active = redis_client.get(killswitch_key) == "true"

        deactivated_segments: List[str] = []
        if killswitch_active:
            deactivated_segments = get_killswitch_deactivated_segments(
                user_id, redis_client
            )

        # Default segments — in production, base status from Zerodha API
        default_segments = [
            ("NSE", True),
            ("BSE", True),
            ("NFO", True),
            ("BFO", False),
        ]

        segments = []
        for seg_name, default_active in default_segments:
            is_deactivated_by_ks = seg_name in deactivated_segments
            # If deactivated by kill switch, mark as inactive
            is_active = (not is_deactivated_by_ks) and default_active
            segments.append(
                SegmentStatus(
                    segment=seg_name,
                    is_active=is_active,
                    deactivated_by_killswitch=is_deactivated_by_ks,
                )
            )

        return segments

    def toggle_segment(
        self, user_id: int, segment: str, activate: bool
    ) -> SegmentStatus:
        """Toggle segment activation via Zerodha API.

        This is a placeholder — actual implementation would call Zerodha Console API
        to activate/deactivate trading segments.

        Args:
            user_id: The user's ID.
            segment: Segment name (NSE, BSE, NFO, BFO).
            activate: True to activate, False to deactivate.

        Returns:
            Updated SegmentStatus.

        Raises:
            ValueError: If segment name is invalid.
        """
        valid_segments = ("NSE", "BSE", "NFO", "BFO")
        if segment.upper() not in valid_segments:
            raise ValueError(
                f"Invalid segment: '{segment}'. Must be one of: {', '.join(valid_segments)}"
            )

        # Placeholder: In production, this would call Zerodha API
        # e.g., zerodha_client.activate_segment(user_id, segment)
        return SegmentStatus(
            segment=segment.upper(),
            is_active=activate,
            deactivated_by_killswitch=False,
        )

    # ------------------------------------------------------------------
    # AI Settings
    # ------------------------------------------------------------------

    def get_ai_settings(self, db: Session, user_id: int) -> AISettings:
        """Get AI configuration for the user.

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.

        Returns:
            AISettings with provider info and feature toggles.
        """
        settings = self._get_user_settings(db, user_id)
        return AISettings(
            provider=settings.ai_provider,
            api_key_configured=bool(settings.ai_provider and settings.ai_provider != ""),
            signal_analysis_enabled=settings.ai_signal_analysis_enabled,
            entry_suggestions_enabled=settings.ai_entry_suggestions_enabled,
            exit_recommendations_enabled=settings.ai_exit_recommendations_enabled,
            market_narrative_enabled=settings.ai_market_narrative_enabled,
            trade_review_enabled=settings.ai_trade_review_enabled,
            risk_warnings_enabled=settings.ai_risk_warnings_enabled,
        )

    def update_ai_settings(
        self, db: Session, user_id: int, settings: dict
    ) -> AISettings:
        """Update AI configuration for the user and cache in Redis.

        Caches AI settings in Redis so the AI worker checks feature flags
        without hitting the DB on each task.

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.
            settings: Dictionary with AI settings fields to update.

        Returns:
            Updated AISettings.

        Raises:
            ValueError: If provider is invalid.
        """
        valid_providers = ("gemini", "claude", "openai")

        if "provider" in settings:
            if settings["provider"] not in valid_providers:
                raise ValueError(
                    f"Invalid AI provider: '{settings['provider']}'. "
                    f"Must be one of: {', '.join(valid_providers)}"
                )

        user_settings = self._get_user_settings(db, user_id)

        # Update only provided fields
        if "provider" in settings:
            user_settings.ai_provider = settings["provider"]
        if "signal_analysis_enabled" in settings:
            user_settings.ai_signal_analysis_enabled = bool(
                settings["signal_analysis_enabled"]
            )
        if "entry_suggestions_enabled" in settings:
            user_settings.ai_entry_suggestions_enabled = bool(
                settings["entry_suggestions_enabled"]
            )
        if "exit_recommendations_enabled" in settings:
            user_settings.ai_exit_recommendations_enabled = bool(
                settings["exit_recommendations_enabled"]
            )
        if "market_narrative_enabled" in settings:
            user_settings.ai_market_narrative_enabled = bool(
                settings["market_narrative_enabled"]
            )
        if "trade_review_enabled" in settings:
            user_settings.ai_trade_review_enabled = bool(
                settings["trade_review_enabled"]
            )
        if "risk_warnings_enabled" in settings:
            user_settings.ai_risk_warnings_enabled = bool(
                settings["risk_warnings_enabled"]
            )

        db.commit()
        db.refresh(user_settings)

        result = self.get_ai_settings(db, user_id)

        # Cache in Redis for AI worker (Requirement 17.2)
        self._cache_ai_settings(user_id, result)

        return result

    # ------------------------------------------------------------------
    # Redis cache helpers — settings propagation to workers
    # Requirements: 5.2, 6.4
    # ------------------------------------------------------------------

    def _cache_strategy_settings(
        self, user_id: int, settings: StrategySettings
    ) -> None:
        """Cache strategy settings in Redis for worker consumption.

        Caches the full strategy settings and a separate watchlist key
        so the scanner worker can quickly read the watchlist without
        parsing the full settings payload.

        Args:
            user_id: The user's ID.
            settings: The strategy settings to cache.
        """
        try:
            redis_client = get_redis_client()

            # Cache full strategy settings
            strategy_key = RedisKeys.user_strategy_settings(user_id)
            redis_client.set(
                strategy_key,
                json.dumps(settings.model_dump(), default=str),
                ttl=SettingsTTL.STRATEGY,
            )

            # Cache watchlist separately for quick scanner worker access
            watchlist_key = RedisKeys.user_watchlist(user_id)
            redis_client.set(
                watchlist_key,
                json.dumps(settings.watchlist),
                ttl=SettingsTTL.WATCHLIST,
            )

            logger.debug(
                "Cached strategy settings in Redis for user %d (watchlist: %d symbols)",
                user_id,
                len(settings.watchlist),
            )
        except Exception as e:
            logger.warning(
                "Failed to cache strategy settings for user %d: %s: %s",
                user_id,
                type(e).__name__,
                str(e),
            )

    def _cache_killswitch_thresholds(
        self, user_id: int, thresholds: KillSwitchThresholdsResponse
    ) -> None:
        """Cache kill switch thresholds in Redis for immediate auto-monitor pickup.

        The auto-monitor worker runs every 5 seconds and reads thresholds
        from this cache key, so changes apply within 5 seconds max.

        Args:
            user_id: The user's ID.
            thresholds: The kill switch thresholds response to cache.
        """
        try:
            redis_client = get_redis_client()

            key = RedisKeys.user_killswitch_thresholds(user_id)
            redis_client.set(
                key,
                json.dumps(thresholds.model_dump(), default=str),
                ttl=SettingsTTL.KILLSWITCH_THRESHOLDS,
            )

            logger.debug(
                "Cached kill switch thresholds in Redis for user %d "
                "(daily_loss=%.2f, profit_target=%.2f, drawdown=%.2f)",
                user_id,
                thresholds.daily_loss_amount,
                thresholds.profit_target_amount,
                thresholds.drawdown_amount,
            )
        except Exception as e:
            logger.warning(
                "Failed to cache kill switch thresholds for user %d: %s: %s",
                user_id,
                type(e).__name__,
                str(e),
            )

    def _cache_ai_settings(self, user_id: int, settings: AISettings) -> None:
        """Cache AI settings in Redis for AI worker feature flag checks.

        The AI worker reads from this key to determine which features
        are enabled before dispatching analysis tasks.

        Args:
            user_id: The user's ID.
            settings: The AI settings to cache.
        """
        try:
            redis_client = get_redis_client()

            key = RedisKeys.user_ai_settings(user_id)
            redis_client.set(
                key,
                json.dumps(settings.model_dump(), default=str),
                ttl=SettingsTTL.AI_SETTINGS,
            )

            logger.debug(
                "Cached AI settings in Redis for user %d (provider=%s)",
                user_id,
                settings.provider,
            )
        except Exception as e:
            logger.warning(
                "Failed to cache AI settings for user %d: %s: %s",
                user_id,
                type(e).__name__,
                str(e),
            )

    # ------------------------------------------------------------------
    # Static cache-reading methods for workers
    # ------------------------------------------------------------------

    @staticmethod
    def get_cached_watchlist(user_id: int) -> Optional[List[str]]:
        """Read the user's watchlist from Redis cache.

        Used by scanner_worker to quickly get the watchlist without
        hitting the database. Returns None if cache miss (worker should
        fall back to DB).

        Args:
            user_id: The user's ID.

        Returns:
            List of watchlist symbols, or None if not cached.
        """
        try:
            redis_client = get_redis_client()
            key = RedisKeys.user_watchlist(user_id)
            cached = redis_client.get(key)
            if cached:
                return json.loads(cached)
            return None
        except Exception as e:
            logger.warning(
                "Failed to read cached watchlist for user %d: %s",
                user_id,
                str(e),
            )
            return None

    @staticmethod
    def get_cached_killswitch_thresholds(user_id: int) -> Optional[dict]:
        """Read kill switch thresholds from Redis cache.

        Used by auto_monitor_worker to get thresholds without DB query.
        Returns None if cache miss (worker should fall back to DB).

        Args:
            user_id: The user's ID.

        Returns:
            Dict with daily_loss_amount, profit_target_amount, drawdown_amount,
            capital — or None if not cached.
        """
        try:
            redis_client = get_redis_client()
            key = RedisKeys.user_killswitch_thresholds(user_id)
            cached = redis_client.get(key)
            if cached:
                return json.loads(cached)
            return None
        except Exception as e:
            logger.warning(
                "Failed to read cached killswitch thresholds for user %d: %s",
                user_id,
                str(e),
            )
            return None

    @staticmethod
    def get_cached_ai_settings(user_id: int) -> Optional[dict]:
        """Read AI settings from Redis cache.

        Used by ai_worker to check feature toggles without DB query.
        Returns None if cache miss (worker should fall back to DB).

        Args:
            user_id: The user's ID.

        Returns:
            Dict with provider and feature toggle booleans, or None if not cached.
        """
        try:
            redis_client = get_redis_client()
            key = RedisKeys.user_ai_settings(user_id)
            cached = redis_client.get(key)
            if cached:
                return json.loads(cached)
            return None
        except Exception as e:
            logger.warning(
                "Failed to read cached AI settings for user %d: %s",
                user_id,
                str(e),
            )
            return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_user_settings(self, db: Session, user_id: int) -> UserSettings:
        """Load UserSettings for a user, creating defaults if not found.

        Args:
            db: SQLAlchemy session.
            user_id: The user's ID.

        Returns:
            UserSettings ORM instance.

        Raises:
            ValueError: If user_id is invalid (non-positive).
        """
        if user_id is None or user_id <= 0:
            raise ValueError("user_id must be a positive integer")

        settings = (
            db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        )

        if settings is None:
            # Create default settings for the user
            settings = UserSettings(user_id=user_id)
            db.add(settings)
            db.commit()
            db.refresh(settings)

        return settings
