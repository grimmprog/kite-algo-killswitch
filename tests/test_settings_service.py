"""Tests for src/services/settings_service.py

Tests:
- get_strategy_settings returns correct StrategySettings from DB
- update_strategy_settings validates and persists settings
- Validation: confidence 50-100, max_trades 1-10, capital > 0, start_time < end_time
- get_killswitch_thresholds returns computed amounts
- update_killswitch_thresholds validates and triggers warning
- Kill switch threshold calculation: amount = capital × percentage / 100
- Warning when daily loss > 25% of capital
- get_segments returns all 4 segments
- toggle_segment validates segment names
- get_ai_settings / update_ai_settings CRUD operations

Implements Requirements: 5.1-5.7, 6.1-6.6
"""

from unittest.mock import MagicMock, patch, PropertyMock
import pytest

from src.services.settings_service import (
    SettingsService,
    StrategySettings,
    KillSwitchThresholds,
    KillSwitchThresholdsResponse,
    SegmentStatus,
    AISettings,
    _validate_time_format,
    _time_before,
    _compute_amount,
    _check_daily_loss_warning,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    """Create a SettingsService instance."""
    return SettingsService()


@pytest.fixture
def mock_db():
    """Create a mock SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def mock_user_settings():
    """Create a mock UserSettings ORM model with default values."""
    settings = MagicMock()
    settings.user_id = 1
    settings.watchlist = ["NIFTY", "BANKNIFTY"]
    settings.trading_start_time = "09:15"
    settings.trading_end_time = "15:30"
    settings.confidence_threshold = 70
    settings.max_trades_per_day = 5
    settings.max_active_trades = 3
    settings.capital = 100000.0
    settings.lot_sizes = {"NIFTY": 25, "BANKNIFTY": 15}
    settings.daily_loss_type = "percentage"
    settings.daily_loss_value = 2.0
    settings.profit_target_type = "percentage"
    settings.profit_target_value = 5.0
    settings.drawdown_type = "percentage"
    settings.drawdown_value = 3.0
    settings.profit_warning_pct = 80.0
    settings.ai_provider = "openai"
    settings.ai_signal_analysis_enabled = True
    settings.ai_entry_suggestions_enabled = True
    settings.ai_exit_recommendations_enabled = True
    settings.ai_market_narrative_enabled = True
    settings.ai_trade_review_enabled = True
    settings.ai_risk_warnings_enabled = True
    return settings


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestValidateTimeFormat:
    """Tests for _validate_time_format helper."""

    def test_valid_times(self):
        assert _validate_time_format("09:15") is True
        assert _validate_time_format("00:00") is True
        assert _validate_time_format("23:59") is True
        assert _validate_time_format("15:30") is True

    def test_invalid_format(self):
        assert _validate_time_format("") is False
        assert _validate_time_format("9:15") is False
        assert _validate_time_format("09-15") is False
        assert _validate_time_format("0915") is False
        assert _validate_time_format("09:60") is False
        assert _validate_time_format("24:00") is False
        assert _validate_time_format("abc") is False


class TestTimeBefore:
    """Tests for _time_before helper."""

    def test_start_before_end(self):
        assert _time_before("09:15", "15:30") is True

    def test_start_equal_end(self):
        assert _time_before("09:15", "09:15") is False

    def test_start_after_end(self):
        assert _time_before("15:30", "09:15") is False


class TestComputeAmount:
    """Tests for _compute_amount helper."""

    def test_percentage_type(self):
        # 100000 × 2 / 100 = 2000
        assert _compute_amount(100000.0, "percentage", 2.0) == 2000.0

    def test_absolute_type(self):
        # absolute returns value directly
        assert _compute_amount(100000.0, "absolute", 5000.0) == 5000.0

    def test_percentage_25_percent(self):
        # 100000 × 25 / 100 = 25000
        assert _compute_amount(100000.0, "percentage", 25.0) == 25000.0


class TestCheckDailyLossWarning:
    """Tests for _check_daily_loss_warning helper."""

    def test_no_warning_percentage_below_25(self):
        result = _check_daily_loss_warning(100000.0, "percentage", 20.0)
        assert result is None

    def test_warning_percentage_above_25(self):
        result = _check_daily_loss_warning(100000.0, "percentage", 30.0)
        assert result is not None
        assert "Warning" in result
        assert "30.0%" in result

    def test_no_warning_absolute_below_25_pct(self):
        # 25% of 100000 = 25000; value 20000 < 25000
        result = _check_daily_loss_warning(100000.0, "absolute", 20000.0)
        assert result is None

    def test_warning_absolute_above_25_pct(self):
        # 25% of 100000 = 25000; value 30000 > 25000
        result = _check_daily_loss_warning(100000.0, "absolute", 30000.0)
        assert result is not None
        assert "Warning" in result

    def test_exactly_25_percent_no_warning(self):
        # Exactly 25% should not trigger (> 25, not >=)
        result = _check_daily_loss_warning(100000.0, "percentage", 25.0)
        assert result is None

    def test_exactly_25_percent_absolute_no_warning(self):
        # Exactly 25000 = 25% of 100000, not > so no warning
        result = _check_daily_loss_warning(100000.0, "absolute", 25000.0)
        assert result is None


# ---------------------------------------------------------------------------
# Strategy Settings tests
# ---------------------------------------------------------------------------


class TestGetStrategySettings:
    """Tests for SettingsService.get_strategy_settings."""

    def test_returns_strategy_settings(self, service, mock_db, mock_user_settings):
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_user_settings
        )

        result = service.get_strategy_settings(mock_db, 1)

        assert isinstance(result, StrategySettings)
        assert result.watchlist == ["NIFTY", "BANKNIFTY"]
        assert result.trading_start_time == "09:15"
        assert result.trading_end_time == "15:30"
        assert result.confidence_threshold == 70
        assert result.max_trades_per_day == 5
        assert result.capital == 100000.0

    def test_invalid_user_id_raises(self, service, mock_db):
        with pytest.raises(ValueError, match="user_id must be a positive"):
            service.get_strategy_settings(mock_db, 0)

    def test_negative_user_id_raises(self, service, mock_db):
        with pytest.raises(ValueError, match="user_id must be a positive"):
            service.get_strategy_settings(mock_db, -1)


class TestUpdateStrategySettings:
    """Tests for SettingsService.update_strategy_settings."""

    def test_valid_update(self, service, mock_db, mock_user_settings):
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_user_settings
        )

        new_settings = StrategySettings(
            watchlist=["NIFTY"],
            trading_start_time="09:30",
            trading_end_time="15:15",
            confidence_threshold=80,
            max_trades_per_day=3,
            max_active_trades=2,
            capital=50000.0,
            lot_sizes={"NIFTY": 50},
        )

        result = service.update_strategy_settings(mock_db, 1, new_settings)

        assert isinstance(result, StrategySettings)
        mock_db.commit.assert_called()

    def test_invalid_start_time_format_raises(self, service, mock_db, mock_user_settings):
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_user_settings
        )

        new_settings = StrategySettings(
            watchlist=["NIFTY"],
            trading_start_time="9:15",  # invalid format
            trading_end_time="15:30",
            confidence_threshold=70,
            max_trades_per_day=5,
            max_active_trades=3,
            capital=100000.0,
            lot_sizes={},
        )

        with pytest.raises(ValueError, match="Invalid trading_start_time"):
            service.update_strategy_settings(mock_db, 1, new_settings)

    def test_invalid_end_time_format_raises(self, service, mock_db, mock_user_settings):
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_user_settings
        )

        new_settings = StrategySettings(
            watchlist=["NIFTY"],
            trading_start_time="09:15",
            trading_end_time="25:30",  # invalid hours
            confidence_threshold=70,
            max_trades_per_day=5,
            max_active_trades=3,
            capital=100000.0,
            lot_sizes={},
        )

        with pytest.raises(ValueError, match="Invalid trading_end_time"):
            service.update_strategy_settings(mock_db, 1, new_settings)

    def test_start_time_not_before_end_time_raises(
        self, service, mock_db, mock_user_settings
    ):
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_user_settings
        )

        new_settings = StrategySettings(
            watchlist=["NIFTY"],
            trading_start_time="15:30",
            trading_end_time="09:15",  # end before start
            confidence_threshold=70,
            max_trades_per_day=5,
            max_active_trades=3,
            capital=100000.0,
            lot_sizes={},
        )

        with pytest.raises(ValueError, match="must be before"):
            service.update_strategy_settings(mock_db, 1, new_settings)

    def test_confidence_below_50_raises_pydantic(self):
        """Pydantic validation catches confidence < 50."""
        with pytest.raises(Exception):
            StrategySettings(
                watchlist=[],
                trading_start_time="09:15",
                trading_end_time="15:30",
                confidence_threshold=49,
                max_trades_per_day=5,
                max_active_trades=3,
                capital=100000.0,
                lot_sizes={},
            )

    def test_confidence_above_100_raises_pydantic(self):
        """Pydantic validation catches confidence > 100."""
        with pytest.raises(Exception):
            StrategySettings(
                watchlist=[],
                trading_start_time="09:15",
                trading_end_time="15:30",
                confidence_threshold=101,
                max_trades_per_day=5,
                max_active_trades=3,
                capital=100000.0,
                lot_sizes={},
            )

    def test_max_trades_below_1_raises_pydantic(self):
        """Pydantic validation catches max_trades < 1."""
        with pytest.raises(Exception):
            StrategySettings(
                watchlist=[],
                trading_start_time="09:15",
                trading_end_time="15:30",
                confidence_threshold=70,
                max_trades_per_day=0,
                max_active_trades=3,
                capital=100000.0,
                lot_sizes={},
            )

    def test_capital_zero_raises_pydantic(self):
        """Pydantic validation catches capital <= 0."""
        with pytest.raises(Exception):
            StrategySettings(
                watchlist=[],
                trading_start_time="09:15",
                trading_end_time="15:30",
                confidence_threshold=70,
                max_trades_per_day=5,
                max_active_trades=3,
                capital=0,
                lot_sizes={},
            )


# ---------------------------------------------------------------------------
# Kill Switch Thresholds tests
# ---------------------------------------------------------------------------


class TestGetKillswitchThresholds:
    """Tests for SettingsService.get_killswitch_thresholds."""

    def test_returns_computed_amounts_percentage(
        self, service, mock_db, mock_user_settings
    ):
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_user_settings
        )

        result = service.get_killswitch_thresholds(mock_db, 1)

        assert isinstance(result, KillSwitchThresholdsResponse)
        # capital=100000, daily_loss_value=2%, so amount = 2000
        assert result.daily_loss_amount == 2000.0
        # profit_target_value=5%, so amount = 5000
        assert result.profit_target_amount == 5000.0
        # drawdown_value=3%, so amount = 3000
        assert result.drawdown_amount == 3000.0
        assert result.capital == 100000.0
        # 2% < 25%, no warning
        assert result.warning is None

    def test_returns_warning_when_daily_loss_above_25_pct(
        self, service, mock_db, mock_user_settings
    ):
        mock_user_settings.daily_loss_value = 30.0  # 30% > 25%
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_user_settings
        )

        result = service.get_killswitch_thresholds(mock_db, 1)

        assert result.warning is not None
        assert "Warning" in result.warning

    def test_absolute_type_computation(self, service, mock_db, mock_user_settings):
        mock_user_settings.daily_loss_type = "absolute"
        mock_user_settings.daily_loss_value = 5000.0
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_user_settings
        )

        result = service.get_killswitch_thresholds(mock_db, 1)

        # absolute: amount = value directly
        assert result.daily_loss_amount == 5000.0
        # 5000 < 25000 (25% of 100000), no warning
        assert result.warning is None


class TestUpdateKillswitchThresholds:
    """Tests for SettingsService.update_killswitch_thresholds."""

    def test_valid_update(self, service, mock_db, mock_user_settings):
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_user_settings
        )

        thresholds = KillSwitchThresholds(
            daily_loss_type="percentage",
            daily_loss_value=3.0,
            profit_target_type="percentage",
            profit_target_value=6.0,
            drawdown_type="absolute",
            drawdown_value=4000.0,
            profit_warning_pct=75.0,
        )

        result = service.update_killswitch_thresholds(mock_db, 1, thresholds)

        assert isinstance(result, KillSwitchThresholdsResponse)
        mock_db.commit.assert_called()

    def test_invalid_daily_loss_type_raises(self, service, mock_db, mock_user_settings):
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_user_settings
        )

        thresholds = KillSwitchThresholds(
            daily_loss_type="invalid",
            daily_loss_value=3.0,
            profit_target_type="percentage",
            profit_target_value=6.0,
            drawdown_type="percentage",
            drawdown_value=3.0,
            profit_warning_pct=75.0,
        )

        with pytest.raises(ValueError, match="daily_loss_type"):
            service.update_killswitch_thresholds(mock_db, 1, thresholds)

    def test_warning_flag_returned(self, service, mock_db, mock_user_settings):
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_user_settings
        )

        # Set capital on mock for the response computation
        mock_user_settings.capital = 100000.0

        thresholds = KillSwitchThresholds(
            daily_loss_type="percentage",
            daily_loss_value=30.0,  # > 25%
            profit_target_type="percentage",
            profit_target_value=5.0,
            drawdown_type="percentage",
            drawdown_value=3.0,
            profit_warning_pct=80.0,
        )

        result = service.update_killswitch_thresholds(mock_db, 1, thresholds)

        assert result.warning is not None


# ---------------------------------------------------------------------------
# Segments tests
# ---------------------------------------------------------------------------


class TestGetSegments:
    """Tests for SettingsService.get_segments."""

    def test_returns_four_segments(self, service):
        result = service.get_segments(user_id=1)

        assert len(result) == 4
        segment_names = [s.segment for s in result]
        assert "NSE" in segment_names
        assert "BSE" in segment_names
        assert "NFO" in segment_names
        assert "BFO" in segment_names

    def test_all_are_segment_status(self, service):
        result = service.get_segments(user_id=1)
        for s in result:
            assert isinstance(s, SegmentStatus)


class TestToggleSegment:
    """Tests for SettingsService.toggle_segment."""

    def test_activate_valid_segment(self, service):
        result = service.toggle_segment(user_id=1, segment="NSE", activate=True)

        assert isinstance(result, SegmentStatus)
        assert result.segment == "NSE"
        assert result.is_active is True

    def test_deactivate_valid_segment(self, service):
        result = service.toggle_segment(user_id=1, segment="NFO", activate=False)

        assert result.is_active is False
        assert result.segment == "NFO"

    def test_case_insensitive_segment(self, service):
        result = service.toggle_segment(user_id=1, segment="nse", activate=True)
        assert result.segment == "NSE"

    def test_invalid_segment_raises(self, service):
        with pytest.raises(ValueError, match="Invalid segment"):
            service.toggle_segment(user_id=1, segment="MCX", activate=True)


# ---------------------------------------------------------------------------
# AI Settings tests
# ---------------------------------------------------------------------------


class TestGetAISettings:
    """Tests for SettingsService.get_ai_settings."""

    def test_returns_ai_settings(self, service, mock_db, mock_user_settings):
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_user_settings
        )

        result = service.get_ai_settings(mock_db, 1)

        assert isinstance(result, AISettings)
        assert result.provider == "openai"
        assert result.signal_analysis_enabled is True
        assert result.api_key_configured is True

    def test_empty_provider_marks_key_unconfigured(
        self, service, mock_db, mock_user_settings
    ):
        mock_user_settings.ai_provider = ""
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_user_settings
        )

        result = service.get_ai_settings(mock_db, 1)
        assert result.api_key_configured is False


class TestUpdateAISettings:
    """Tests for SettingsService.update_ai_settings."""

    def test_update_provider(self, service, mock_db, mock_user_settings):
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_user_settings
        )

        result = service.update_ai_settings(mock_db, 1, {"provider": "gemini"})

        assert isinstance(result, AISettings)
        mock_db.commit.assert_called()

    def test_invalid_provider_raises(self, service, mock_db, mock_user_settings):
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_user_settings
        )

        with pytest.raises(ValueError, match="Invalid AI provider"):
            service.update_ai_settings(mock_db, 1, {"provider": "invalid_llm"})

    def test_partial_update_only_toggles(self, service, mock_db, mock_user_settings):
        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_user_settings
        )

        service.update_ai_settings(
            mock_db, 1, {"signal_analysis_enabled": False}
        )

        assert mock_user_settings.ai_signal_analysis_enabled is False
        mock_db.commit.assert_called()
