"""Unit tests for AITradingService consolidation analysis methods (Task 7.5).

Tests cover:
- analyze_consolidation: false breakout detection, fallback heuristic, LLM integration
- rank_consolidations: sorting and best_trade designation
- assess_breakout: real-time breakout assessment logic

Validates: Requirements 20.1, 20.2, 20.3, 20.4, 20.5
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch

from src.services.ai_trading_service import (
    AIProvider,
    AITradingService,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def service():
    """Create an AITradingService with mocked _make_request (error fallback)."""
    svc = AITradingService(provider=AIProvider.GEMINI, api_key="test-key")
    svc._make_request = MagicMock(return_value={"error": "AI unavailable"})
    return svc


@pytest.fixture
def service_with_llm():
    """Create an AITradingService with a successful LLM mock response."""
    svc = AITradingService(provider=AIProvider.GEMINI, api_key="test-key")
    svc._make_request = MagicMock(return_value={
        "breakout_probability": 72.0,
        "predicted_direction": "up",
        "expected_move_pct": 3.5,
        "false_breakout_risk": False,
        "false_breakout_reasons": [],
        "assessment": "Strong setup with volume confirmation.",
    })
    return svc


@pytest.fixture
def base_pattern():
    """A standard consolidation pattern."""
    return {
        "range_high": 200.0,
        "range_low": 190.0,
        "avg_price": 195.0,
        "candle_count": 8,
        "duration_minutes": 24,
        "volume_avg": 5000.0,
        "breakout_volume": 7000.0,
        "breakout_direction": "up",
    }


@pytest.fixture
def base_market_context():
    """A standard market context."""
    return {
        "trend_direction": "bullish",
        "volume_profile": {"avg": 5000, "current": 6000},
        "time_of_day": "09:45",
        "key_levels": {"support": [185.0], "resistance": [210.0]},
        "vwap": 194.5,
    }


# ============================================================
# Tests: analyze_consolidation — False Breakout Detection (Req 20.3)
# ============================================================


class TestAnalyzeConsolidationFalseBreakout:
    """Test false breakout warning detection logic."""

    def test_no_false_breakout_when_all_conditions_favorable(
        self, service, base_pattern, base_market_context
    ):
        """No false breakout risk when volume exceeds avg, trend aligned, duration >= 15 min."""
        result = service.analyze_consolidation(base_pattern, base_market_context)

        assert result["false_breakout_risk"] is False
        assert result["false_breakout_reasons"] == []

    def test_false_breakout_volume_below_average(
        self, service, base_pattern, base_market_context
    ):
        """False breakout warning when breakout volume < average volume."""
        base_pattern["breakout_volume"] = 3000.0  # Below volume_avg of 5000

        result = service.analyze_consolidation(base_pattern, base_market_context)

        assert result["false_breakout_risk"] is True
        assert "Volume below average during breakout" in result["false_breakout_reasons"]

    def test_false_breakout_against_broader_trend(
        self, service, base_pattern, base_market_context
    ):
        """False breakout warning when breakout direction opposes broader trend."""
        base_market_context["trend_direction"] = "bearish"
        base_pattern["breakout_direction"] = "up"

        result = service.analyze_consolidation(base_pattern, base_market_context)

        assert result["false_breakout_risk"] is True
        assert "Breakout against broader trend" in result["false_breakout_reasons"]

    def test_false_breakout_short_consolidation(
        self, service, base_pattern, base_market_context
    ):
        """False breakout warning when consolidation duration < 15 minutes."""
        base_pattern["duration_minutes"] = 12

        result = service.analyze_consolidation(base_pattern, base_market_context)

        assert result["false_breakout_risk"] is True
        assert "Consolidation duration less than 15 minutes" in result["false_breakout_reasons"]

    def test_multiple_false_breakout_reasons(
        self, service, base_pattern, base_market_context
    ):
        """Multiple false breakout reasons can be triggered simultaneously."""
        base_pattern["breakout_volume"] = 2000.0
        base_pattern["duration_minutes"] = 10
        base_market_context["trend_direction"] = "bearish"
        base_pattern["breakout_direction"] = "up"

        result = service.analyze_consolidation(base_pattern, base_market_context)

        assert result["false_breakout_risk"] is True
        assert len(result["false_breakout_reasons"]) == 3

    def test_bearish_trend_with_down_breakout_no_warning(
        self, service, base_pattern, base_market_context
    ):
        """No trend warning when breakout aligns with bearish trend."""
        base_market_context["trend_direction"] = "bearish"
        base_pattern["breakout_direction"] = "down"

        result = service.analyze_consolidation(base_pattern, base_market_context)

        assert "Breakout against broader trend" not in result["false_breakout_reasons"]


# ============================================================
# Tests: analyze_consolidation — Fallback Heuristic (Req 20.1, 20.2)
# ============================================================


class TestAnalyzeConsolidationFallback:
    """Test the deterministic fallback heuristic when LLM is unavailable."""

    def test_fallback_returns_required_fields(
        self, service, base_pattern, base_market_context
    ):
        """Fallback response includes all required AIConsolidationAnalysis fields."""
        result = service.analyze_consolidation(base_pattern, base_market_context)

        assert "breakout_probability" in result
        assert "predicted_direction" in result
        assert "expected_move_pct" in result
        assert "false_breakout_risk" in result
        assert "false_breakout_reasons" in result
        assert "assessment" in result

    def test_fallback_probability_clamped_0_100(
        self, service, base_pattern, base_market_context
    ):
        """Fallback probability is clamped between 0 and 100."""
        result = service.analyze_consolidation(base_pattern, base_market_context)

        assert 0.0 <= result["breakout_probability"] <= 100.0

    def test_fallback_tighter_range_higher_probability(self, service, base_market_context):
        """Tighter consolidation range increases breakout probability."""
        tight_pattern = {
            "range_high": 200.0,
            "range_low": 197.0,  # 3/198.5 = ~1.5% range
            "avg_price": 198.5,
            "candle_count": 10,
            "duration_minutes": 20,
            "volume_avg": 5000.0,
            "breakout_volume": 6000.0,
            "breakout_direction": "up",
        }
        wide_pattern = {
            "range_high": 200.0,
            "range_low": 170.0,  # 30/185 = ~16% range
            "avg_price": 185.0,
            "candle_count": 10,
            "duration_minutes": 20,
            "volume_avg": 5000.0,
            "breakout_volume": 6000.0,
            "breakout_direction": "up",
        }

        result_tight = service.analyze_consolidation(tight_pattern, base_market_context)
        result_wide = service.analyze_consolidation(wide_pattern, base_market_context)

        assert result_tight["breakout_probability"] > result_wide["breakout_probability"]

    def test_fallback_more_candles_higher_probability(self, service, base_market_context):
        """More candles in consolidation increases probability."""
        few_candles = {
            "range_high": 200.0, "range_low": 195.0, "avg_price": 197.5,
            "candle_count": 4, "duration_minutes": 20,
            "volume_avg": 5000.0, "breakout_volume": 6000.0,
            "breakout_direction": "up",
        }
        many_candles = {
            "range_high": 200.0, "range_low": 195.0, "avg_price": 197.5,
            "candle_count": 12, "duration_minutes": 20,
            "volume_avg": 5000.0, "breakout_volume": 6000.0,
            "breakout_direction": "up",
        }

        result_few = service.analyze_consolidation(few_candles, base_market_context)
        result_many = service.analyze_consolidation(many_candles, base_market_context)

        assert result_many["breakout_probability"] > result_few["breakout_probability"]

    def test_fallback_predicted_direction_from_breakout(
        self, service, base_pattern, base_market_context
    ):
        """Fallback predicted direction comes from breakout_direction."""
        base_pattern["breakout_direction"] = "down"
        result = service.analyze_consolidation(base_pattern, base_market_context)

        assert result["predicted_direction"] == "down"

    def test_fallback_assessment_mentions_ai_unavailable(
        self, service, base_pattern, base_market_context
    ):
        """Fallback assessment notes that AI was unavailable."""
        result = service.analyze_consolidation(base_pattern, base_market_context)

        assert "AI unavailable" in result["assessment"]


# ============================================================
# Tests: analyze_consolidation — LLM Integration (Req 20.1, 20.2)
# ============================================================


class TestAnalyzeConsolidationLLM:
    """Test LLM integration in analyze_consolidation."""

    def test_llm_response_merged_with_local_false_breakout(self, service_with_llm):
        """LLM response is merged with locally-detected false breakout reasons."""
        pattern = {
            "range_high": 200.0, "range_low": 190.0, "avg_price": 195.0,
            "candle_count": 8, "duration_minutes": 10,  # < 15 min trigger
            "volume_avg": 5000.0, "breakout_volume": 7000.0,
            "breakout_direction": "up",
        }
        market_context = {"trend_direction": "bullish"}

        result = service_with_llm.analyze_consolidation(pattern, market_context)

        # Local analysis should add duration < 15 min reason
        assert "Consolidation duration less than 15 minutes" in result["false_breakout_reasons"]
        assert result["false_breakout_risk"] is True

    def test_llm_response_used_when_successful(self, service_with_llm):
        """LLM-provided breakout_probability is returned when LLM succeeds."""
        pattern = {
            "range_high": 200.0, "range_low": 190.0, "avg_price": 195.0,
            "candle_count": 8, "duration_minutes": 24,
            "volume_avg": 5000.0, "breakout_volume": 7000.0,
            "breakout_direction": "up",
        }
        market_context = {"trend_direction": "bullish"}

        result = service_with_llm.analyze_consolidation(pattern, market_context)

        assert result["breakout_probability"] == 72.0
        assert result["predicted_direction"] == "up"
        assert result["expected_move_pct"] == 3.5


# ============================================================
# Tests: rank_consolidations (Req 20.4)
# ============================================================


class TestRankConsolidations:
    """Test rank_consolidations sorting and best_trade designation."""

    def test_empty_patterns_returns_empty(self, service):
        """Empty pattern list returns empty result."""
        result = service.rank_consolidations([], {"trend_direction": "bullish"})
        assert result == []

    def test_single_pattern_is_best_trade(self, service, base_pattern, base_market_context):
        """Single pattern is always the best trade."""
        result = service.rank_consolidations([base_pattern], base_market_context)

        assert len(result) == 1
        assert result[0]["best_trade"] is True

    def test_multiple_patterns_sorted_descending(self, service, base_market_context):
        """Multiple patterns are sorted by breakout_probability descending."""
        patterns = [
            {"range_high": 200, "range_low": 195, "avg_price": 197.5,
             "candle_count": 4, "duration_minutes": 10,
             "volume_avg": 5000, "breakout_volume": 3000,
             "breakout_direction": "up"},  # Low probability (short, low vol)
            {"range_high": 200, "range_low": 198, "avg_price": 199,
             "candle_count": 12, "duration_minutes": 30,
             "volume_avg": 5000, "breakout_volume": 8000,
             "breakout_direction": "up"},  # High probability (tight, long, high vol)
        ]

        result = service.rank_consolidations(patterns, base_market_context)

        assert len(result) == 2
        assert result[0]["breakout_probability"] >= result[1]["breakout_probability"]
        assert result[0]["best_trade"] is True
        assert result[1]["best_trade"] is False


# ============================================================
# Tests: assess_breakout (Req 20.5)
# ============================================================


class TestAssessBreakout:
    """Test real-time breakout assessment logic."""

    @pytest.fixture
    def breakout_service(self):
        """Service with mocked LLM that returns error (forces local fallback)."""
        svc = AITradingService(provider=AIProvider.GEMINI, api_key="test-key")
        svc._make_request = MagicMock(return_value={"error": "AI unavailable"})
        return svc

    def test_confirmed_breakout_volume_and_trend_aligned(self, breakout_service):
        """Confirmed breakout when volume supports and trend is aligned."""
        pattern = {
            "range_high": 200.0, "range_low": 190.0, "avg_price": 195.0,
            "candle_count": 8, "duration_minutes": 20,
            "volume_avg": 5000.0,
        }
        breakout_data = {
            "breakout_price": 205.0,
            "breakout_volume": 7000.0,
            "direction": "up",
            "trend_direction": "bullish",
        }

        result = breakout_service.assess_breakout(pattern, breakout_data)

        assert result["assessment"] == "Confirmed breakout — volume supports"
        assert result["confidence"] > 70.0

    def test_suspicious_breakout_low_volume(self, breakout_service):
        """Suspicious when volume is below average but trend aligned."""
        pattern = {
            "range_high": 200.0, "range_low": 190.0, "avg_price": 195.0,
            "candle_count": 8, "duration_minutes": 20,
            "volume_avg": 5000.0,
        }
        breakout_data = {
            "breakout_price": 205.0,
            "breakout_volume": 3000.0,  # Below average
            "direction": "up",
            "trend_direction": "bullish",
        }

        result = breakout_service.assess_breakout(pattern, breakout_data)

        assert result["assessment"] == "Suspicious — low volume, wait for retest"

    def test_false_breakout_low_volume_and_against_trend(self, breakout_service):
        """False breakout when volume is low AND against trend."""
        pattern = {
            "range_high": 200.0, "range_low": 190.0, "avg_price": 195.0,
            "candle_count": 8, "duration_minutes": 20,
            "volume_avg": 5000.0,
        }
        breakout_data = {
            "breakout_price": 205.0,
            "breakout_volume": 3000.0,  # Below average
            "direction": "up",
            "trend_direction": "bearish",  # Against trend
        }

        result = breakout_service.assess_breakout(pattern, breakout_data)

        assert result["assessment"] == "False breakout likely — avoid"

    def test_confirmed_breakout_volume_supports_neutral_trend(self, breakout_service):
        """Confirmed breakout with volume when trend is neutral (neutral counts as aligned)."""
        pattern = {
            "range_high": 200.0, "range_low": 190.0, "avg_price": 195.0,
            "candle_count": 8, "duration_minutes": 20,
            "volume_avg": 5000.0,
        }
        breakout_data = {
            "breakout_price": 205.0,
            "breakout_volume": 7000.0,
            "direction": "up",
            "trend_direction": "neutral",
        }

        result = breakout_service.assess_breakout(pattern, breakout_data)

        assert result["assessment"] == "Confirmed breakout — volume supports"

    def test_assess_breakout_returns_details(self, breakout_service):
        """Assessment includes details explaining the reasoning."""
        pattern = {
            "range_high": 200.0, "range_low": 190.0, "avg_price": 195.0,
            "candle_count": 8, "duration_minutes": 20,
            "volume_avg": 5000.0,
        }
        breakout_data = {
            "breakout_price": 205.0,
            "breakout_volume": 7000.0,
            "direction": "up",
            "trend_direction": "bullish",
        }

        result = breakout_service.assess_breakout(pattern, breakout_data)

        assert "details" in result
        assert "breakout volume exceeds average" in result["details"]
        assert "aligned with broader trend" in result["details"]

    def test_assess_breakout_confidence_clamped(self, breakout_service):
        """Confidence is always between 0 and 100."""
        pattern = {
            "range_high": 200.0, "range_low": 190.0, "avg_price": 195.0,
            "candle_count": 8, "duration_minutes": 20,
            "volume_avg": 5000.0,
        }
        breakout_data = {
            "breakout_price": 205.0,
            "breakout_volume": 7000.0,
            "direction": "up",
            "trend_direction": "bullish",
        }

        result = breakout_service.assess_breakout(pattern, breakout_data)

        assert 0.0 <= result["confidence"] <= 100.0

    def test_assess_breakout_uses_llm_valid_assessment(self):
        """When LLM returns a valid assessment, it's used instead of local."""
        svc = AITradingService(provider=AIProvider.GEMINI, api_key="test-key")
        svc._make_request = MagicMock(return_value={
            "assessment": "Suspicious — low volume, wait for retest",
            "confidence": 65.0,
            "details": "LLM analysis indicates caution.",
        })

        pattern = {
            "range_high": 200.0, "range_low": 190.0, "avg_price": 195.0,
            "candle_count": 8, "duration_minutes": 20,
            "volume_avg": 5000.0,
        }
        breakout_data = {
            "breakout_price": 205.0,
            "breakout_volume": 7000.0,
            "direction": "up",
            "trend_direction": "bullish",
        }

        result = svc.assess_breakout(pattern, breakout_data)

        # LLM response should be used since it's a valid assessment
        assert result["assessment"] == "Suspicious — low volume, wait for retest"
        assert result["confidence"] == 65.0

    def test_assess_breakout_ignores_invalid_llm_assessment(self):
        """When LLM returns invalid assessment string, local fallback is used."""
        svc = AITradingService(provider=AIProvider.GEMINI, api_key="test-key")
        svc._make_request = MagicMock(return_value={
            "assessment": "Some random invalid assessment",
            "confidence": 80.0,
            "details": "Invalid.",
        })

        pattern = {
            "range_high": 200.0, "range_low": 190.0, "avg_price": 195.0,
            "candle_count": 8, "duration_minutes": 20,
            "volume_avg": 5000.0,
        }
        breakout_data = {
            "breakout_price": 205.0,
            "breakout_volume": 7000.0,
            "direction": "up",
            "trend_direction": "bullish",
        }

        result = svc.assess_breakout(pattern, breakout_data)

        # Should fall back to local assessment (volume supports + trend aligned)
        assert result["assessment"] == "Confirmed breakout — volume supports"
