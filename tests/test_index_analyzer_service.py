"""Unit tests for IndexAnalyzerService.

Tests cover:
- compute_composite_score: weighted formula correctness
- recommend_trade: best index selection, CE/PE choice, strike calculation
- analyze_indices: raw data processing and metric computation
- Edge cases: no data available, single index, all bearish

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from src.services.index_analyzer_service import (
    IndexAnalyzerService,
    IndexMetrics,
    IndexRecommendation,
    STRIKE_STEPS,
    TREND_SCORES,
)


@pytest.fixture
def service():
    return IndexAnalyzerService()


# --- compute_composite_score tests ---


class TestComputeCompositeScore:
    def test_all_max_bullish(self, service):
        """momentum=100, volume=100, trend=bullish(100) → 100."""
        score = service.compute_composite_score(100.0, 100.0, "bullish")
        assert score == 100.0

    def test_all_zero_bearish(self, service):
        """momentum=0, volume=0, trend=bearish(0) → 0."""
        score = service.compute_composite_score(0.0, 0.0, "bearish")
        assert score == 0.0

    def test_neutral_mid_values(self, service):
        """momentum=50, volume=50, trend=neutral(50) → 50."""
        score = service.compute_composite_score(50.0, 50.0, "neutral")
        assert score == 50.0

    def test_weighted_formula(self, service):
        """Verify: 80*0.4 + 60*0.3 + bullish(100)*0.3 = 32 + 18 + 30 = 80."""
        score = service.compute_composite_score(80.0, 60.0, "bullish")
        assert score == 80.0

    def test_bearish_reduces_score(self, service):
        """Verify: 80*0.4 + 60*0.3 + bearish(0)*0.3 = 32 + 18 + 0 = 50."""
        score = service.compute_composite_score(80.0, 60.0, "bearish")
        assert score == 50.0

    def test_unknown_trend_defaults_to_neutral(self, service):
        """Unknown trend direction treated as neutral (50)."""
        score = service.compute_composite_score(100.0, 100.0, "unknown")
        # 100*0.4 + 100*0.3 + 50*0.3 = 40 + 30 + 15 = 85
        assert score == 85.0

    def test_case_insensitive_trend(self, service):
        """Trend direction should be case-insensitive."""
        score_lower = service.compute_composite_score(70.0, 70.0, "bullish")
        score_upper = service.compute_composite_score(70.0, 70.0, "Bullish")
        assert score_lower == score_upper


# --- recommend_trade tests ---


class TestRecommendTrade:
    def test_picks_highest_composite_score(self, service):
        """Should recommend the index with highest composite score."""
        metrics = [
            IndexMetrics(
                symbol="NIFTY 50",
                current_price=22500.0,
                change_1h_pct=0.5,
                change_daily_pct=1.0,
                momentum_score=60.0,
                volume_score=50.0,
                trend_direction="bullish",
                composite_score=69.0,
                data_available=True,
            ),
            IndexMetrics(
                symbol="BANK NIFTY",
                current_price=47200.0,
                change_1h_pct=1.2,
                change_daily_pct=1.5,
                momentum_score=85.0,
                volume_score=70.0,
                trend_direction="bullish",
                composite_score=85.0,
                data_available=True,
            ),
            IndexMetrics(
                symbol="SENSEX",
                current_price=73000.0,
                change_1h_pct=0.3,
                change_daily_pct=0.6,
                momentum_score=40.0,
                volume_score=30.0,
                trend_direction="neutral",
                composite_score=40.0,
                data_available=True,
            ),
        ]
        result = service.recommend_trade(metrics)
        assert result is not None
        assert result.best_index == "BANK NIFTY"

    def test_bullish_recommends_ce(self, service):
        """Bullish trend → CE option type."""
        metrics = [
            IndexMetrics(
                symbol="NIFTY 50",
                current_price=22500.0,
                change_1h_pct=0.5,
                change_daily_pct=1.0,
                momentum_score=80.0,
                volume_score=70.0,
                trend_direction="bullish",
                composite_score=83.0,
                data_available=True,
            ),
        ]
        result = service.recommend_trade(metrics)
        assert result is not None
        assert result.option_type == "CE"

    def test_bearish_recommends_pe(self, service):
        """Bearish trend → PE option type."""
        metrics = [
            IndexMetrics(
                symbol="NIFTY 50",
                current_price=22500.0,
                change_1h_pct=-0.5,
                change_daily_pct=-1.0,
                momentum_score=80.0,
                volume_score=70.0,
                trend_direction="bearish",
                composite_score=53.0,
                data_available=True,
            ),
        ]
        result = service.recommend_trade(metrics)
        assert result is not None
        assert result.option_type == "PE"

    def test_neutral_recommends_pe(self, service):
        """Neutral trend → PE (not bullish means PE)."""
        metrics = [
            IndexMetrics(
                symbol="NIFTY 50",
                current_price=22500.0,
                change_1h_pct=0.0,
                change_daily_pct=0.0,
                momentum_score=50.0,
                volume_score=50.0,
                trend_direction="neutral",
                composite_score=50.0,
                data_available=True,
            ),
        ]
        result = service.recommend_trade(metrics)
        assert result is not None
        assert result.option_type == "PE"

    def test_strike_nifty_step_50(self, service):
        """NIFTY 50 uses strike step of 50."""
        metrics = [
            IndexMetrics(
                symbol="NIFTY 50",
                current_price=22437.0,
                change_1h_pct=0.5,
                change_daily_pct=1.0,
                momentum_score=80.0,
                volume_score=70.0,
                trend_direction="bullish",
                composite_score=83.0,
                data_available=True,
            ),
        ]
        result = service.recommend_trade(metrics)
        assert result is not None
        assert result.recommended_strike == 22450.0
        assert result.strike_step == 50

    def test_strike_banknifty_step_100(self, service):
        """BANK NIFTY uses strike step of 100."""
        metrics = [
            IndexMetrics(
                symbol="BANK NIFTY",
                current_price=47230.0,
                change_1h_pct=1.0,
                change_daily_pct=1.5,
                momentum_score=85.0,
                volume_score=70.0,
                trend_direction="bullish",
                composite_score=85.0,
                data_available=True,
            ),
        ]
        result = service.recommend_trade(metrics)
        assert result is not None
        assert result.recommended_strike == 47200.0
        assert result.strike_step == 100

    def test_strike_sensex_step_100(self, service):
        """SENSEX uses strike step of 100."""
        metrics = [
            IndexMetrics(
                symbol="SENSEX",
                current_price=72550.0,
                change_1h_pct=0.8,
                change_daily_pct=1.2,
                momentum_score=90.0,
                volume_score=80.0,
                trend_direction="bullish",
                composite_score=91.0,
                data_available=True,
            ),
        ]
        result = service.recommend_trade(metrics)
        assert result is not None
        assert result.recommended_strike == 72600.0
        assert result.strike_step == 100

    def test_filters_unavailable_indices(self, service):
        """Should skip indices where data_available=False."""
        metrics = [
            IndexMetrics(
                symbol="NIFTY 50",
                current_price=0.0,
                change_1h_pct=0.0,
                change_daily_pct=0.0,
                momentum_score=0.0,
                volume_score=0.0,
                trend_direction="neutral",
                composite_score=0.0,
                data_available=False,
            ),
            IndexMetrics(
                symbol="BANK NIFTY",
                current_price=47200.0,
                change_1h_pct=1.0,
                change_daily_pct=1.5,
                momentum_score=85.0,
                volume_score=70.0,
                trend_direction="bullish",
                composite_score=85.0,
                data_available=True,
            ),
        ]
        result = service.recommend_trade(metrics)
        assert result is not None
        assert result.best_index == "BANK NIFTY"

    def test_all_unavailable_returns_none(self, service):
        """Should return None if no indices have data available."""
        metrics = [
            IndexMetrics(
                symbol="NIFTY 50",
                current_price=0.0,
                change_1h_pct=0.0,
                change_daily_pct=0.0,
                momentum_score=0.0,
                volume_score=0.0,
                trend_direction="neutral",
                composite_score=0.0,
                data_available=False,
            ),
        ]
        result = service.recommend_trade(metrics)
        assert result is None

    def test_empty_list_returns_none(self, service):
        """Should return None for an empty metrics list."""
        result = service.recommend_trade([])
        assert result is None


# --- analyze_indices tests ---


class TestAnalyzeIndices:
    def test_computes_metrics_for_all_indices(self, service):
        """Should return metrics for all provided indices."""
        market_data = {
            "NIFTY 50": {
                "current_price": 22500.0,
                "change_1h_pct": 0.5,
                "change_daily_pct": 1.0,
                "momentum_score": 70.0,
                "volume_score": 60.0,
                "trend_direction": "bullish",
            },
            "BANK NIFTY": {
                "current_price": 47200.0,
                "change_1h_pct": 1.2,
                "change_daily_pct": 1.5,
                "momentum_score": 85.0,
                "volume_score": 70.0,
                "trend_direction": "bullish",
            },
        }
        results = service.analyze_indices(market_data)
        assert len(results) == 2
        symbols = {r.symbol for r in results}
        assert symbols == {"NIFTY 50", "BANK NIFTY"}

    def test_computes_composite_score_correctly(self, service):
        """Should compute composite score using the weighted formula."""
        market_data = {
            "NIFTY 50": {
                "current_price": 22500.0,
                "change_1h_pct": 0.5,
                "change_daily_pct": 1.0,
                "momentum_score": 80.0,
                "volume_score": 60.0,
                "trend_direction": "bullish",
            },
        }
        results = service.analyze_indices(market_data)
        assert len(results) == 1
        # 80*0.4 + 60*0.3 + 100*0.3 = 32 + 18 + 30 = 80
        assert results[0].composite_score == 80.0

    def test_handles_unavailable_data(self, service):
        """Should create zeroed metrics for unavailable indices."""
        market_data = {
            "SENSEX": {
                "data_available": False,
            },
        }
        results = service.analyze_indices(market_data)
        assert len(results) == 1
        assert results[0].symbol == "SENSEX"
        assert results[0].data_available is False
        assert results[0].composite_score == 0.0
        assert results[0].momentum_score == 0.0

    def test_defaults_data_available_to_true(self, service):
        """When data_available not provided, defaults to True."""
        market_data = {
            "NIFTY 50": {
                "current_price": 22500.0,
                "change_1h_pct": 0.5,
                "change_daily_pct": 1.0,
                "momentum_score": 70.0,
                "volume_score": 60.0,
                "trend_direction": "neutral",
            },
        }
        results = service.analyze_indices(market_data)
        assert results[0].data_available is True

    def test_empty_market_data(self, service):
        """Empty market data returns empty list."""
        results = service.analyze_indices({})
        assert results == []


# --- _nearest_strike tests ---


class TestNearestStrike:
    def test_exact_step_boundary(self):
        """Price exactly at a step should return that value."""
        assert IndexAnalyzerService._nearest_strike(22500.0, 50) == 22500.0
        assert IndexAnalyzerService._nearest_strike(47200.0, 100) == 47200.0

    def test_rounds_down(self):
        """Price just below midpoint rounds down."""
        assert IndexAnalyzerService._nearest_strike(22510.0, 50) == 22500.0
        assert IndexAnalyzerService._nearest_strike(47240.0, 100) == 47200.0

    def test_rounds_up(self):
        """Price above midpoint rounds up."""
        assert IndexAnalyzerService._nearest_strike(22480.0, 50) == 22500.0
        assert IndexAnalyzerService._nearest_strike(47260.0, 100) == 47300.0

    def test_midpoint_rounds_up(self):
        """Python's round() rounds halves to even; for step=50, midpoint at 25."""
        # 22525 → nearest to 22500 or 22550; round(22525/50)=round(450.5)=450 → 22500
        # (Python banker's rounding: 450.5 → 450 since 450 is even)
        assert IndexAnalyzerService._nearest_strike(22525.0, 50) == 22500.0
        # 22575 → round(22575/50)=round(451.5)=452 → 22600
        assert IndexAnalyzerService._nearest_strike(22575.0, 50) == 22600.0
