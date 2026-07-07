"""Unit tests for AITradingService.detect_risk_anomalies method.

Tests the enhanced implementation that combines:
- Deterministic behavioral checks (break suggestion, revenge trading)
- Risk rule violation blocking (max trades, trading hours, loss limit)
- Market condition warnings (VIX, volume, gap, expiry day)

Validates: Requirements 24.1, 24.2, 24.3, 24.4, 24.5, 24.6
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock

from src.services.ai_trading_service import AITradingService, AIProvider


@pytest.fixture
def service():
    """Create AITradingService with mocked LLM client."""
    svc = AITradingService(provider=AIProvider.GEMINI, api_key="test-key")
    # Mock _make_request to avoid actual LLM calls
    svc._make_request = MagicMock(return_value={"error": True, "message": "mocked"})
    return svc


class TestBreakSuggestion:
    """Req 24.3: Break suggestion after 3+ consecutive losses."""

    def test_break_suggested_at_3_losses(self, service):
        """Break warning emitted when 3 consecutive losses."""
        user_state = {"consecutive_losses": 3}
        result = service.detect_risk_anomalies(user_state, {})

        behavioral_warnings = [
            w for w in result["warnings"]
            if w["category"] == "behavioral" and "break" in w["message"].lower()
        ]
        assert len(behavioral_warnings) == 1
        assert behavioral_warnings[0]["severity"] == "warning"
        assert "3 consecutive losses" in behavioral_warnings[0]["message"]

    def test_break_suggested_at_5_losses(self, service):
        """Break warning emitted when 5 consecutive losses."""
        user_state = {"consecutive_losses": 5}
        result = service.detect_risk_anomalies(user_state, {})

        behavioral_warnings = [
            w for w in result["warnings"]
            if w["category"] == "behavioral" and "break" in w["message"].lower()
        ]
        assert len(behavioral_warnings) == 1
        assert "5 consecutive losses" in behavioral_warnings[0]["message"]

    def test_no_break_at_2_losses(self, service):
        """No break warning when only 2 consecutive losses."""
        user_state = {"consecutive_losses": 2}
        result = service.detect_risk_anomalies(user_state, {})

        behavioral_warnings = [
            w for w in result["warnings"]
            if w["category"] == "behavioral" and "break" in w["message"].lower()
        ]
        assert len(behavioral_warnings) == 0

    def test_no_break_at_0_losses(self, service):
        """No break warning when no losses."""
        user_state = {"consecutive_losses": 0}
        result = service.detect_risk_anomalies(user_state, {})

        behavioral_warnings = [
            w for w in result["warnings"]
            if w["category"] == "behavioral" and "break" in w["message"].lower()
        ]
        assert len(behavioral_warnings) == 0

    def test_no_break_when_key_missing(self, service):
        """No break warning when consecutive_losses key is absent."""
        result = service.detect_risk_anomalies({}, {})

        behavioral_warnings = [
            w for w in result["warnings"]
            if w["category"] == "behavioral" and "break" in w["message"].lower()
        ]
        assert len(behavioral_warnings) == 0


class TestRevengeTradingDetection:
    """Req 24.5: Revenge trading detection within 5 min of loss."""

    def test_revenge_trading_detected(self, service):
        """Revenge trading flagged within 5 min on correlated symbol."""
        user_state = {
            "last_loss_time_minutes": 3.0,
            "same_or_correlated_symbol": True,
        }
        result = service.detect_risk_anomalies(user_state, {})

        revenge_warnings = [
            w for w in result["warnings"]
            if "revenge" in w["message"].lower()
        ]
        assert len(revenge_warnings) == 1
        assert revenge_warnings[0]["severity"] == "critical"
        assert revenge_warnings[0]["category"] == "behavioral"

    def test_revenge_trading_at_boundary(self, service):
        """Revenge trading detected at exactly 5 minutes."""
        user_state = {
            "last_loss_time_minutes": 5.0,
            "same_or_correlated_symbol": True,
        }
        result = service.detect_risk_anomalies(user_state, {})

        revenge_warnings = [
            w for w in result["warnings"]
            if "revenge" in w["message"].lower()
        ]
        assert len(revenge_warnings) == 1

    def test_no_revenge_trading_after_5_minutes(self, service):
        """No revenge trading warning after 5 minutes."""
        user_state = {
            "last_loss_time_minutes": 6.0,
            "same_or_correlated_symbol": True,
        }
        result = service.detect_risk_anomalies(user_state, {})

        revenge_warnings = [
            w for w in result["warnings"]
            if "revenge" in w["message"].lower()
        ]
        assert len(revenge_warnings) == 0

    def test_no_revenge_trading_different_symbol(self, service):
        """No revenge trading when symbol is not correlated."""
        user_state = {
            "last_loss_time_minutes": 2.0,
            "same_or_correlated_symbol": False,
        }
        result = service.detect_risk_anomalies(user_state, {})

        revenge_warnings = [
            w for w in result["warnings"]
            if "revenge" in w["message"].lower()
        ]
        assert len(revenge_warnings) == 0

    def test_no_revenge_trading_when_no_recent_loss(self, service):
        """No revenge trading when last_loss_time_minutes is absent."""
        user_state = {"same_or_correlated_symbol": True}
        result = service.detect_risk_anomalies(user_state, {})

        revenge_warnings = [
            w for w in result["warnings"]
            if "revenge" in w["message"].lower()
        ]
        assert len(revenge_warnings) == 0


class TestRiskRuleViolationBlocking:
    """Req 24.4: Risk rule violations require explicit acknowledgment."""

    def test_max_trades_violation(self, service):
        """Max trades violation detected and requires acknowledgment."""
        user_state = {"current_trades": 5, "max_trades": 5}
        result = service.detect_risk_anomalies(user_state, {})

        violations = [
            w for w in result["warnings"]
            if w["category"] == "rule_violation"
        ]
        assert len(violations) == 1
        assert "Max trades" in violations[0]["message"]
        assert violations[0]["requires_acknowledgment"] is True

    def test_loss_limit_violation(self, service):
        """Loss limit violation detected with acknowledgment required."""
        user_state = {"daily_loss": 5000.0, "loss_limit": 4000.0}
        result = service.detect_risk_anomalies(user_state, {})

        violations = [
            w for w in result["warnings"]
            if w["category"] == "rule_violation" and "loss" in w["message"].lower()
        ]
        assert len(violations) == 1
        assert violations[0]["severity"] == "critical"
        assert violations[0]["requires_acknowledgment"] is True

    def test_trading_hours_violation(self, service):
        """Trading outside hours flagged."""
        user_state = {
            "current_hour": 8.0,
            "trading_start_hour": 9.25,
            "trading_end_hour": 15.5,
            "current_trades": 0,
            "max_trades": 10,
        }
        result = service.detect_risk_anomalies(user_state, {})

        violations = [
            w for w in result["warnings"]
            if "trading hours" in w["message"].lower()
        ]
        assert len(violations) == 1
        assert violations[0]["requires_acknowledgment"] is True

    def test_requires_acknowledgment_in_response(self, service):
        """Overall response indicates acknowledgment required."""
        user_state = {"current_trades": 10, "max_trades": 5}
        result = service.detect_risk_anomalies(user_state, {})

        assert result["requires_acknowledgment"] is True


class TestMarketConditionWarnings:
    """Req 24.1: Market condition warnings."""

    def test_elevated_vix_warning(self, service):
        """Warning when VIX > 20."""
        market_data = {"vix": 25.5}
        result = service.detect_risk_anomalies({}, market_data)

        vix_warnings = [
            w for w in result["warnings"]
            if "vix" in w["message"].lower()
        ]
        assert len(vix_warnings) == 1
        assert vix_warnings[0]["severity"] == "warning"
        assert vix_warnings[0]["category"] == "market_condition"

    def test_no_vix_warning_below_20(self, service):
        """No VIX warning when VIX <= 20."""
        market_data = {"vix": 15.0}
        result = service.detect_risk_anomalies({}, market_data)

        vix_warnings = [
            w for w in result["warnings"]
            if "vix" in w["message"].lower()
        ]
        assert len(vix_warnings) == 0

    def test_vix_spike_highlighted(self, service):
        """VIX spike percentage shown when change > 10%."""
        market_data = {"vix": 25.0, "vix_change_pct": 15.0}
        result = service.detect_risk_anomalies({}, market_data)

        vix_warnings = [
            w for w in result["warnings"]
            if "vix" in w["message"].lower()
        ]
        assert len(vix_warnings) == 1
        assert "spike" in vix_warnings[0]["message"].lower()

    def test_low_volume_warning(self, service):
        """Warning when volume ratio < 0.5."""
        market_data = {"volume_ratio": 0.3}
        result = service.detect_risk_anomalies({}, market_data)

        volume_warnings = [
            w for w in result["warnings"]
            if "volume" in w["message"].lower()
        ]
        assert len(volume_warnings) == 1
        assert volume_warnings[0]["severity"] == "info"

    def test_no_volume_warning_normal(self, service):
        """No volume warning when ratio is normal."""
        market_data = {"volume_ratio": 0.8}
        result = service.detect_risk_anomalies({}, market_data)

        volume_warnings = [
            w for w in result["warnings"]
            if "volume" in w["message"].lower()
        ]
        assert len(volume_warnings) == 0

    def test_gap_up_warning(self, service):
        """Warning on gap-up opening > 1%."""
        market_data = {"gap_pct": 2.5}
        result = service.detect_risk_anomalies({}, market_data)

        gap_warnings = [
            w for w in result["warnings"]
            if "gap" in w["message"].lower()
        ]
        assert len(gap_warnings) == 1
        assert "gap-up" in gap_warnings[0]["message"].lower()

    def test_gap_down_warning(self, service):
        """Warning on gap-down opening > 1%."""
        market_data = {"gap_pct": -1.5}
        result = service.detect_risk_anomalies({}, market_data)

        gap_warnings = [
            w for w in result["warnings"]
            if "gap" in w["message"].lower()
        ]
        assert len(gap_warnings) == 1
        assert "gap-down" in gap_warnings[0]["message"].lower()

    def test_no_gap_warning_small_gap(self, service):
        """No gap warning when gap <= 1%."""
        market_data = {"gap_pct": 0.5}
        result = service.detect_risk_anomalies({}, market_data)

        gap_warnings = [
            w for w in result["warnings"]
            if "gap" in w["message"].lower()
        ]
        assert len(gap_warnings) == 0

    def test_expiry_day_warning(self, service):
        """Info warning on expiry day."""
        market_data = {"is_expiry_day": True}
        result = service.detect_risk_anomalies({}, market_data)

        expiry_warnings = [
            w for w in result["warnings"]
            if "expiry" in w["message"].lower()
        ]
        assert len(expiry_warnings) == 1
        assert expiry_warnings[0]["severity"] == "info"

    def test_no_expiry_warning_normal_day(self, service):
        """No expiry warning on non-expiry day."""
        market_data = {"is_expiry_day": False}
        result = service.detect_risk_anomalies({}, market_data)

        expiry_warnings = [
            w for w in result["warnings"]
            if "expiry" in w["message"].lower()
        ]
        assert len(expiry_warnings) == 0


class TestResponseStructure:
    """Verify the response dict structure is correct."""

    def test_empty_state_returns_valid_structure(self, service):
        """Empty inputs return proper structure with no warnings."""
        result = service.detect_risk_anomalies({}, {})

        assert "warnings" in result
        assert "warning_count" in result
        assert "has_critical" in result
        assert "requires_acknowledgment" in result
        assert isinstance(result["warnings"], list)
        assert result["warning_count"] == 0
        assert result["has_critical"] is False
        assert result["requires_acknowledgment"] is False

    def test_has_critical_flag_set(self, service):
        """has_critical is True when any critical warning exists."""
        user_state = {
            "last_loss_time_minutes": 2.0,
            "same_or_correlated_symbol": True,
        }
        result = service.detect_risk_anomalies(user_state, {})

        assert result["has_critical"] is True

    def test_warning_count_matches_list_length(self, service):
        """warning_count equals length of warnings list."""
        user_state = {
            "consecutive_losses": 4,
            "last_loss_time_minutes": 3.0,
            "same_or_correlated_symbol": True,
        }
        market_data = {"vix": 25.0, "is_expiry_day": True}
        result = service.detect_risk_anomalies(user_state, market_data)

        assert result["warning_count"] == len(result["warnings"])
        # Should have: break, revenge, vix, expiry = 4
        assert result["warning_count"] == 4

    def test_combined_warnings_from_all_categories(self, service):
        """All categories (behavioral, rule_violation, market_condition) can coexist."""
        user_state = {
            "consecutive_losses": 3,
            "current_trades": 10,
            "max_trades": 5,
        }
        market_data = {"vix": 22.0}
        result = service.detect_risk_anomalies(user_state, market_data)

        categories = set(w["category"] for w in result["warnings"])
        assert "behavioral" in categories
        assert "rule_violation" in categories
        assert "market_condition" in categories
