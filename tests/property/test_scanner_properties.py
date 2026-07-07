"""Property-based tests for ScannerService (Task 3.2).

Uses Hypothesis to verify consolidation detection and breakout detection
correctness properties.

**Validates: Requirements 2.2, 2.3**

Properties:
- Property 1: Consolidation Detection Correctness
  Verify consolidation identified iff spread < 15% avg price over 6+ candles
- Property 2: Breakout Detection Correctness
  Verify breakout flagged iff price > range_high × 1.10
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from hypothesis import given, strategies as st, settings, assume

from src.services.scanner_service import ScannerService, ConsolidationPattern


# ============================================================
# Custom Strategies — Candle Data Generation
# ============================================================


def candle_strategy(base_price: float, max_spread_pct: float):
    """Generate a single candle dict with controlled spread relative to base_price.

    The candle's high and low are constrained so that per-candle variation
    is bounded, allowing us to control the overall window spread via
    the base price and max_spread_pct.
    """
    half_spread = base_price * max_spread_pct / 2
    return st.fixed_dictionaries({
        "open": st.floats(
            min_value=base_price - half_spread,
            max_value=base_price + half_spread,
            allow_nan=False, allow_infinity=False,
        ),
        "high": st.floats(
            min_value=base_price,
            max_value=base_price + half_spread,
            allow_nan=False, allow_infinity=False,
        ),
        "low": st.floats(
            min_value=base_price - half_spread,
            max_value=base_price,
            allow_nan=False, allow_infinity=False,
        ),
        "close": st.floats(
            min_value=base_price - half_spread,
            max_value=base_price + half_spread,
            allow_nan=False, allow_infinity=False,
        ),
        "volume": st.integers(min_value=100, max_value=100000),
    })


@st.composite
def tight_consolidation_candles(draw):
    """Generate candle data that MUST form a consolidation pattern.

    Strategy: Generate 6+ candles where all highs and lows are within
    a tight band (spread < 15% of avg price). We achieve this by
    generating candles around a base price with individual variation < 7%
    so the overall spread stays well under 15%.
    """
    base_price = draw(st.floats(min_value=50.0, max_value=5000.0,
                                allow_nan=False, allow_infinity=False))
    num_candles = draw(st.integers(min_value=6, max_value=30))

    # Keep per-candle spread tight: max 5% per candle from base
    # This ensures overall window spread < 10% < 15% threshold
    max_individual_spread_pct = 0.05
    half_spread = base_price * max_individual_spread_pct / 2

    candles = []
    for _ in range(num_candles):
        high = draw(st.floats(
            min_value=base_price,
            max_value=base_price + half_spread,
            allow_nan=False, allow_infinity=False,
        ))
        low = draw(st.floats(
            min_value=base_price - half_spread,
            max_value=base_price,
            allow_nan=False, allow_infinity=False,
        ))
        open_price = draw(st.floats(
            min_value=low, max_value=high,
            allow_nan=False, allow_infinity=False,
        ))
        close_price = draw(st.floats(
            min_value=low, max_value=high,
            allow_nan=False, allow_infinity=False,
        ))
        volume = draw(st.integers(min_value=100, max_value=100000))

        candles.append({
            "open": open_price,
            "high": high,
            "low": low,
            "close": close_price,
            "volume": volume,
        })

    return base_price, candles


@st.composite
def wide_spread_candles(draw):
    """Generate candle data where spread >= 15% of avg price (no consolidation).

    Strategy: Generate candles with an intentionally wide spread by placing
    at least one high and one low far apart from the base price.
    """
    base_price = draw(st.floats(min_value=100.0, max_value=5000.0,
                                allow_nan=False, allow_infinity=False))
    num_candles = draw(st.integers(min_value=6, max_value=20))

    # We want (max_high - min_low) / avg_price >= 0.15
    # Set spread to at least 20% to be safely above 15%
    spread_pct = draw(st.floats(min_value=0.20, max_value=0.50,
                                allow_nan=False, allow_infinity=False))

    candles = []
    for i in range(num_candles):
        if i == 0:
            # First candle: push high up significantly
            high = base_price * (1 + spread_pct / 2)
            low = base_price * 0.99
        elif i == 1:
            # Second candle: push low down significantly
            high = base_price * 1.01
            low = base_price * (1 - spread_pct / 2)
        else:
            # Other candles: stay near base
            half = base_price * 0.02
            high = draw(st.floats(
                min_value=base_price, max_value=base_price + half,
                allow_nan=False, allow_infinity=False,
            ))
            low = draw(st.floats(
                min_value=base_price - half, max_value=base_price,
                allow_nan=False, allow_infinity=False,
            ))

        open_price = (high + low) / 2
        close_price = (high + low) / 2
        volume = draw(st.integers(min_value=100, max_value=100000))

        candles.append({
            "open": open_price,
            "high": high,
            "low": low,
            "close": close_price,
            "volume": volume,
        })

    return base_price, candles


# ============================================================
# Property 1: Consolidation Detection Correctness
# ============================================================


class TestConsolidationDetectionProperty:
    """Property-based tests for consolidation detection correctness.

    **Validates: Requirements 2.2**

    Core invariant:
    - Consolidation is detected iff (max_high - min_low) / avg_price < 0.15
      over at least 6 consecutive candles.
    """

    @given(data=tight_consolidation_candles())
    @settings(max_examples=100, deadline=None)
    def test_consolidation_detected_when_spread_below_threshold(self, data):
        """When spread < 15% avg price over 6+ candles, detect_consolidation MUST return a pattern.

        **Validates: Requirements 2.2**

        Property: For any set of 6+ candles where (max_high - min_low) / avg_close < 0.15,
        detect_consolidation returns a non-None ConsolidationPattern.
        """
        base_price, candles = data

        # Verify our generated data actually has spread < 15%
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]
        max_high = max(highs)
        min_low = min(lows)
        avg_price = sum(closes) / len(closes)

        assume(avg_price > 0)
        spread_ratio = (max_high - min_low) / avg_price
        assume(spread_ratio < 0.15)
        assume(len(candles) >= 6)

        scanner = ScannerService()
        result = scanner.detect_consolidation("TEST", candles)

        assert result is not None, (
            f"Expected consolidation detection for {len(candles)} candles "
            f"with spread ratio {spread_ratio:.4f} (< 0.15), but got None"
        )
        assert isinstance(result, ConsolidationPattern)
        assert result.candle_count >= 6
        assert result.symbol == "TEST"

    @given(data=wide_spread_candles())
    @settings(max_examples=100, deadline=None)
    def test_no_consolidation_when_spread_above_threshold(self, data):
        """When spread >= 15% avg price, detect_consolidation MUST return None.

        **Validates: Requirements 2.2**

        Property: For any set of candles where (max_high - min_low) / avg_close >= 0.15
        across ALL possible 6+ candle windows, detect_consolidation returns None.
        """
        base_price, candles = data

        # Verify our generated data has spread >= 15% over the full window
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]
        max_high = max(highs)
        min_low = min(lows)
        avg_price = sum(closes) / len(closes)

        assume(avg_price > 0)
        spread_ratio = (max_high - min_low) / avg_price
        assume(spread_ratio >= 0.15)

        # Also verify that no sub-window of 6+ candles has spread < 15%
        # (the service checks sub-windows too)
        has_tight_subwindow = False
        for start in range(len(candles)):
            for end in range(start + 6, len(candles) + 1):
                window = candles[start:end]
                w_highs = [c["high"] for c in window]
                w_lows = [c["low"] for c in window]
                w_closes = [c["close"] for c in window]
                w_avg = sum(w_closes) / len(w_closes)
                if w_avg > 0:
                    w_spread = (max(w_highs) - min(w_lows)) / w_avg
                    if w_spread < 0.15:
                        has_tight_subwindow = True
                        break
            if has_tight_subwindow:
                break

        # Only assert None when no sub-window qualifies
        assume(not has_tight_subwindow)

        scanner = ScannerService()
        result = scanner.detect_consolidation("TEST", candles)

        assert result is None, (
            f"Expected no consolidation for candles with spread ratio "
            f"{spread_ratio:.4f} (>= 0.15), but got a pattern with "
            f"{result.candle_count} candles"
        )

    @given(
        num_candles=st.integers(min_value=1, max_value=5),
        base_price=st.floats(min_value=50.0, max_value=5000.0,
                             allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, deadline=None)
    def test_no_consolidation_with_fewer_than_6_candles(self, num_candles, base_price):
        """When fewer than 6 candles are provided, detect_consolidation MUST return None.

        **Validates: Requirements 2.2**

        Property: Regardless of spread, consolidation requires minimum 6 candles.
        """
        candles = []
        for _ in range(num_candles):
            candles.append({
                "open": base_price,
                "high": base_price * 1.001,
                "low": base_price * 0.999,
                "close": base_price,
                "volume": 1000,
            })

        scanner = ScannerService()
        result = scanner.detect_consolidation("TEST", candles)

        assert result is None, (
            f"Expected None for {num_candles} candles (< 6 minimum), "
            f"but got a pattern"
        )


# ============================================================
# Property 2: Breakout Detection Correctness
# ============================================================


class TestBreakoutDetectionProperty:
    """Property-based tests for breakout detection correctness.

    **Validates: Requirements 2.3**

    Core invariant:
    - Breakout is flagged iff current_price > range_high × 1.10
    """

    @given(
        range_high=st.floats(min_value=10.0, max_value=10000.0,
                             allow_nan=False, allow_infinity=False),
        price_multiplier=st.floats(min_value=1.101, max_value=2.0,
                                   allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_breakout_detected_when_price_above_threshold(
        self, range_high, price_multiplier
    ):
        """When current_price > range_high * 1.10, check_breakout MUST return True.

        **Validates: Requirements 2.3**

        Property: For any range_high and any current_price that exceeds
        range_high × 1.10, the breakout check returns True.
        """
        current_price = range_high * price_multiplier
        assume(current_price > range_high * 1.10)

        pattern = ConsolidationPattern(
            symbol="TEST",
            range_high=range_high,
            range_low=range_high * 0.90,
            avg_price=range_high * 0.95,
            candle_count=6,
            duration_minutes=18,
        )

        scanner = ScannerService()
        result = scanner.check_breakout(pattern, current_price)

        assert result is True, (
            f"Expected breakout=True for price {current_price:.2f} > "
            f"threshold {range_high * 1.10:.2f} (range_high={range_high:.2f} × 1.10), "
            f"but got False"
        )

    @given(
        range_high=st.floats(min_value=10.0, max_value=10000.0,
                             allow_nan=False, allow_infinity=False),
        price_multiplier=st.floats(min_value=0.5, max_value=1.10,
                                   allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_no_breakout_when_price_at_or_below_threshold(
        self, range_high, price_multiplier
    ):
        """When current_price <= range_high * 1.10, check_breakout MUST return False.

        **Validates: Requirements 2.3**

        Property: For any range_high and any current_price at or below
        range_high × 1.10, the breakout check returns False.
        """
        current_price = range_high * price_multiplier
        assume(current_price <= range_high * 1.10)

        pattern = ConsolidationPattern(
            symbol="TEST",
            range_high=range_high,
            range_low=range_high * 0.90,
            avg_price=range_high * 0.95,
            candle_count=6,
            duration_minutes=18,
        )

        scanner = ScannerService()
        result = scanner.check_breakout(pattern, current_price)

        assert result is False, (
            f"Expected breakout=False for price {current_price:.2f} <= "
            f"threshold {range_high * 1.10:.2f} (range_high={range_high:.2f} × 1.10), "
            f"but got True"
        )

    @given(
        range_high=st.floats(min_value=10.0, max_value=10000.0,
                             allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, deadline=None)
    def test_breakout_boundary_at_exactly_10_percent(self, range_high):
        """At exactly range_high * 1.10, check_breakout MUST return False (not strictly above).

        **Validates: Requirements 2.3**

        Property: The breakout condition is strictly greater than (>), not
        greater-than-or-equal (>=). At exactly the threshold, no breakout.
        """
        current_price = range_high * 1.10

        pattern = ConsolidationPattern(
            symbol="TEST",
            range_high=range_high,
            range_low=range_high * 0.90,
            avg_price=range_high * 0.95,
            candle_count=6,
            duration_minutes=18,
        )

        scanner = ScannerService()
        result = scanner.check_breakout(pattern, current_price)

        assert result is False, (
            f"Expected breakout=False at exact boundary price "
            f"{current_price:.2f} == range_high({range_high:.2f}) × 1.10, "
            f"but got True. Breakout requires strictly above threshold."
        )
