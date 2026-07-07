"""Property-based tests for risk metrics consistency (Task 23.4).

Uses Hypothesis to verify that the risk engine's compute functions are
deterministic and mathematically consistent: calling them multiple times
on the same input always produces the same output, and aggregate metrics
equal the sum of individual components.

**Validates: Requirements 6.3.5, 1.4.2, 1.4.3, 1.4.4**

Sub-tasks:
- 23.4.1: Generate random positions (varying quantities, P&L, greeks, margin)
- 23.4.2: Compute risk twice (call compute_live_pnl, compute_greeks, compute_margin_used)
- 23.4.3: Verify consistency (determinism + mathematical properties)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock
from hypothesis import given, strategies as st, settings
from dataclasses import dataclass
from typing import List, Dict

from src.workers.risk_engine_worker import RiskEngineWorker


# ============================================================
# 23.4.1: Custom Strategies - Generate Random Positions
# ============================================================

VALID_SYMBOLS = [
    "NIFTY23DEC21000CE",
    "NIFTY23DEC21000PE",
    "BANKNIFTY23DEC45000CE",
    "BANKNIFTY23DEC45000PE",
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
]

VALID_EXCHANGES = ["NSE", "NFO", "BSE", "BFO"]


def position_strategy():
    """Generate a single random position with realistic trading values."""
    return st.fixed_dictionaries({
        "tradingsymbol": st.sampled_from(VALID_SYMBOLS),
        "exchange": st.sampled_from(VALID_EXCHANGES),
        "quantity": st.integers(min_value=-500, max_value=500),
        "pnl": st.floats(min_value=-100000.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
        "delta": st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        "gamma": st.floats(min_value=0.0, max_value=0.1, allow_nan=False, allow_infinity=False),
        "vega": st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        "margin": st.floats(min_value=0.0, max_value=500000.0, allow_nan=False, allow_infinity=False),
    })


def positions_list_strategy():
    """Generate a list of random positions (1-10 positions)."""
    return st.lists(position_strategy(), min_size=1, max_size=10)


# ============================================================
# Test Infrastructure
# ============================================================


def create_risk_engine(user_id: int = 1) -> RiskEngineWorker:
    """Create a RiskEngineWorker with mocked dependencies for computation tests."""
    kite_mock = MagicMock()
    redis_mock = MagicMock()
    db_mock = MagicMock()

    return RiskEngineWorker(
        user_id=user_id,
        kite_client=kite_mock,
        redis_client=redis_mock,
        db_session=db_mock,
    )


# ============================================================
# 23.4.2 & 23.4.3: Property Tests - Compute Twice & Verify Consistency
# ============================================================


class TestRiskMetricsConsistencyProperty:
    """Property-based tests for risk metrics consistency.

    **Validates: Requirements 6.3.5, 1.4.2, 1.4.3, 1.4.4**

    Core invariants:
    1. Determinism: same input always produces same output
    2. Additivity: total P&L = sum of individual P&Ls
    3. Greeks linearity: net_delta = sum(delta * qty) for each position
    4. Margin additivity: total margin = sum of individual margins
    """

    @given(positions=positions_list_strategy())
    @settings(max_examples=100, deadline=None)
    def test_compute_live_pnl_is_deterministic(self, positions):
        """Computing P&L twice on the same positions yields the same result.

        **Validates: Requirements 6.3.5, 1.4.2**

        Property: For any list of positions, compute_live_pnl(positions) called
        twice returns identical results.
        """
        engine = create_risk_engine()

        result_1 = engine.compute_live_pnl(positions)
        result_2 = engine.compute_live_pnl(positions)

        assert result_1 == result_2, (
            f"compute_live_pnl is non-deterministic: "
            f"first call returned {result_1}, second call returned {result_2}"
        )

    @given(positions=positions_list_strategy())
    @settings(max_examples=100, deadline=None)
    def test_compute_greeks_is_deterministic(self, positions):
        """Computing Greeks twice on the same positions yields the same result.

        **Validates: Requirements 6.3.5, 1.4.3**

        Property: For any list of positions, compute_greeks(positions) called
        twice returns identical dicts.
        """
        engine = create_risk_engine()

        result_1 = engine.compute_greeks(positions)
        result_2 = engine.compute_greeks(positions)

        assert result_1 == result_2, (
            f"compute_greeks is non-deterministic: "
            f"first call returned {result_1}, second call returned {result_2}"
        )

    @given(positions=positions_list_strategy())
    @settings(max_examples=100, deadline=None)
    def test_compute_margin_used_is_deterministic(self, positions):
        """Computing margin twice on the same positions yields the same result.

        **Validates: Requirements 6.3.5, 1.4.4**

        Property: For any list of positions, compute_margin_used(positions) called
        twice returns identical results.
        """
        engine = create_risk_engine()

        result_1 = engine.compute_margin_used(positions)
        result_2 = engine.compute_margin_used(positions)

        assert result_1 == result_2, (
            f"compute_margin_used is non-deterministic: "
            f"first call returned {result_1}, second call returned {result_2}"
        )

    @given(positions=positions_list_strategy())
    @settings(max_examples=100, deadline=None)
    def test_pnl_equals_sum_of_individual_pnls(self, positions):
        """Total P&L equals the sum of each position's pnl field.

        **Validates: Requirements 6.3.5, 1.4.2**

        Property: compute_live_pnl(positions) == sum(pos['pnl'] for pos in positions)
        This verifies the mathematical correctness of the aggregation.
        """
        engine = create_risk_engine()

        total_pnl = engine.compute_live_pnl(positions)
        expected_pnl = sum(float(pos.get("pnl", 0)) for pos in positions)

        assert abs(total_pnl - expected_pnl) < 1e-6, (
            f"P&L mismatch: compute_live_pnl returned {total_pnl}, "
            f"but sum of individual P&Ls is {expected_pnl}"
        )

    @given(positions=positions_list_strategy())
    @settings(max_examples=100, deadline=None)
    def test_net_delta_equals_sum_of_delta_times_quantity(self, positions):
        """Net delta equals sum(delta * quantity) for each position.

        **Validates: Requirements 6.3.5, 1.4.3**

        Property: compute_greeks(positions)['net_delta'] == sum(delta_i * qty_i)
        This verifies the linearity of Greeks aggregation.
        """
        engine = create_risk_engine()

        greeks = engine.compute_greeks(positions)
        expected_delta = sum(
            float(pos.get("delta", 0)) * float(pos.get("quantity", 0))
            for pos in positions
        )

        assert abs(greeks["net_delta"] - expected_delta) < 1e-6, (
            f"net_delta mismatch: compute_greeks returned {greeks['net_delta']}, "
            f"but sum(delta*qty) is {expected_delta}"
        )

    @given(positions=positions_list_strategy())
    @settings(max_examples=100, deadline=None)
    def test_net_gamma_equals_sum_of_gamma_times_quantity(self, positions):
        """Net gamma equals sum(gamma * quantity) for each position.

        **Validates: Requirements 6.3.5, 1.4.3**

        Property: compute_greeks(positions)['net_gamma'] == sum(gamma_i * qty_i)
        """
        engine = create_risk_engine()

        greeks = engine.compute_greeks(positions)
        expected_gamma = sum(
            float(pos.get("gamma", 0)) * float(pos.get("quantity", 0))
            for pos in positions
        )

        assert abs(greeks["net_gamma"] - expected_gamma) < 1e-6, (
            f"net_gamma mismatch: compute_greeks returned {greeks['net_gamma']}, "
            f"but sum(gamma*qty) is {expected_gamma}"
        )

    @given(positions=positions_list_strategy())
    @settings(max_examples=100, deadline=None)
    def test_net_vega_equals_sum_of_vega_times_quantity(self, positions):
        """Net vega equals sum(vega * quantity) for each position.

        **Validates: Requirements 6.3.5, 1.4.3**

        Property: compute_greeks(positions)['net_vega'] == sum(vega_i * qty_i)
        """
        engine = create_risk_engine()

        greeks = engine.compute_greeks(positions)
        expected_vega = sum(
            float(pos.get("vega", 0)) * float(pos.get("quantity", 0))
            for pos in positions
        )

        assert abs(greeks["net_vega"] - expected_vega) < 1e-6, (
            f"net_vega mismatch: compute_greeks returned {greeks['net_vega']}, "
            f"but sum(vega*qty) is {expected_vega}"
        )

    @given(positions=positions_list_strategy())
    @settings(max_examples=100, deadline=None)
    def test_margin_equals_sum_of_individual_margins(self, positions):
        """Total margin equals the sum of each position's margin field.

        **Validates: Requirements 6.3.5, 1.4.4**

        Property: compute_margin_used(positions) == sum(pos['margin'] for pos in positions)
        """
        engine = create_risk_engine()

        total_margin = engine.compute_margin_used(positions)
        expected_margin = sum(float(pos.get("margin", 0)) for pos in positions)

        assert abs(total_margin - expected_margin) < 1e-6, (
            f"Margin mismatch: compute_margin_used returned {total_margin}, "
            f"but sum of individual margins is {expected_margin}"
        )

    @given(positions=positions_list_strategy())
    @settings(max_examples=100, deadline=None)
    def test_empty_positions_returns_zero_for_all_metrics(self, positions):
        """Empty positions list returns zero for all metrics.

        **Validates: Requirements 6.3.5**

        Property: For empty input, all compute functions return 0 / zeros.
        """
        engine = create_risk_engine()

        # Test with empty list
        assert engine.compute_live_pnl([]) == 0.0
        assert engine.compute_greeks([]) == {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}
        assert engine.compute_margin_used([]) == 0.0

        # Test with None
        assert engine.compute_live_pnl(None) == 0.0
        assert engine.compute_greeks(None) == {"net_delta": 0.0, "net_gamma": 0.0, "net_vega": 0.0}
        assert engine.compute_margin_used(None) == 0.0

    @given(positions=positions_list_strategy())
    @settings(max_examples=100, deadline=None)
    def test_all_metrics_computed_together_are_consistent(self, positions):
        """Computing all metrics together yields consistent results with individual calls.

        **Validates: Requirements 6.3.5**

        Property: Computing pnl, greeks, and margin in sequence does not
        introduce side effects that would change subsequent computation results.
        """
        engine = create_risk_engine()

        # Compute all three metrics
        pnl = engine.compute_live_pnl(positions)
        greeks = engine.compute_greeks(positions)
        margin = engine.compute_margin_used(positions)

        # Compute again in reverse order
        margin_2 = engine.compute_margin_used(positions)
        greeks_2 = engine.compute_greeks(positions)
        pnl_2 = engine.compute_live_pnl(positions)

        assert pnl == pnl_2, f"P&L changed between calls: {pnl} vs {pnl_2}"
        assert greeks == greeks_2, f"Greeks changed between calls: {greeks} vs {greeks_2}"
        assert margin == margin_2, f"Margin changed between calls: {margin} vs {margin_2}"
