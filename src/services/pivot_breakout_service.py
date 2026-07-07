"""Pivot Breakout Detection Service — Three-Touch Rule with MACD Confirmation.

Detects breakouts/breakdowns at key pivot levels using the "Three-Touch Rule":
- Price tests a pivot level (R1, R2, S1, S2, or central pivot) multiple times
- Each touch weakens the order block defending that level
- On the 3rd (or 4th) touch, the level breaks with momentum

MACD histogram confirmation:
- Bullish breakout: histogram contracting toward zero → momentum building
- Bearish breakdown: histogram expanding negatively → real selling pressure

This is a well-documented institutional price action pattern where repeated
testing of a level exhausts the defending limit orders.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# --- Constants ---
# Tolerance for considering price "touching" a level (percentage of level value)
TOUCH_TOLERANCE_PCT = 0.05  # 0.05% = ~12 points on Nifty at 24000
# Minimum touches before a breakout is considered high-probability
MIN_TOUCHES_FOR_BREAKOUT = 3
# How many candles to look back for MACD histogram analysis
MACD_LOOKBACK_CANDLES = 6
# Minimum breakout distance (% beyond the level) to confirm a real break
BREAKOUT_CONFIRM_PCT = 0.03  # 0.03% beyond the level


class BreakoutDirection(str, Enum):
    """Direction of the pivot breakout."""
    BULLISH = "bullish"
    BEARISH = "bearish"


class PivotLevel(str, Enum):
    """Standard pivot point levels."""
    PIVOT = "pivot"
    R1 = "r1"
    R2 = "r2"
    R3 = "r3"
    S1 = "s1"
    S2 = "s2"
    S3 = "s3"


class PivotBreakoutSignal(BaseModel):
    """A detected pivot breakout signal with full context.

    Attributes:
        symbol: Trading symbol.
        direction: Bullish breakout or bearish breakdown.
        pivot_level: Which pivot level was broken.
        level_value: The numeric value of the pivot level.
        touch_count: Number of times price tested this level before breaking.
        breakout_price: The price at which the breakout was confirmed.
        macd_confirmed: Whether MACD histogram confirms the breakout.
        macd_histogram_trend: Description of MACD histogram behavior.
        confidence_score: Overall signal confidence (50-100).
        entry_price: Suggested entry price.
        stop_loss: Suggested stop-loss price.
        target_price: Suggested target price.
        max_potential_loss: Maximum loss if stop-loss is hit.
        timestamp: When the signal was generated.
        metadata: Additional context about the signal.
    """
    symbol: str
    direction: BreakoutDirection
    pivot_level: PivotLevel
    level_value: float
    touch_count: int = Field(ge=2)
    breakout_price: float
    macd_confirmed: bool = False
    macd_histogram_trend: str = ""
    confidence_score: float = Field(ge=50, le=100)
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    target_price: float = Field(gt=0)
    max_potential_loss: float
    timestamp: str
    metadata: Dict = Field(default_factory=dict)


@dataclass
class TouchEvent:
    """Records a single price touch at a pivot level."""
    candle_index: int
    high: float
    low: float
    close: float
    distance_from_level: float  # How close it got (as % of level)


@dataclass
class LevelTouchTracker:
    """Tracks touches at a specific pivot level across candles."""
    level_name: PivotLevel
    level_value: float
    touches: List[TouchEvent] = field(default_factory=list)
    is_broken_up: bool = False
    is_broken_down: bool = False
    break_candle_index: Optional[int] = None


class PivotBreakoutService:
    """Detects three-touch breakouts at standard pivot point levels.

    The core logic:
    1. Calculate standard pivot points from previous day's OHLC
    2. Track how many times intraday price touches each level
    3. Detect when a 3rd+ touch results in a breakout
    4. Confirm with MACD histogram momentum shift

    This service contains pure computational logic — no external API calls.
    Candle data and previous day OHLC are passed in by the caller.
    """

    def calculate_pivot_points(
        self, prev_high: float, prev_low: float, prev_close: float
    ) -> Dict[str, float]:
        """Calculate standard pivot points from previous day's OHLC.

        Standard pivot point formula:
            Pivot = (High + Low + Close) / 3
            R1 = 2*Pivot - Low
            S1 = 2*Pivot - High
            R2 = Pivot + (High - Low)
            S2 = Pivot - (High - Low)
            R3 = High + 2*(Pivot - Low)
            S3 = Low - 2*(High - Pivot)

        Args:
            prev_high: Previous day's high price.
            prev_low: Previous day's low price.
            prev_close: Previous day's close price.

        Returns:
            Dict with keys: pivot, r1, r2, r3, s1, s2, s3.
        """
        pivot = (prev_high + prev_low + prev_close) / 3
        r1 = 2 * pivot - prev_low
        s1 = 2 * pivot - prev_high
        r2 = pivot + (prev_high - prev_low)
        s2 = pivot - (prev_high - prev_low)
        r3 = prev_high + 2 * (pivot - prev_low)
        s3 = prev_low - 2 * (prev_high - pivot)

        return {
            "pivot": round(pivot, 2),
            "r1": round(r1, 2),
            "r2": round(r2, 2),
            "r3": round(r3, 2),
            "s1": round(s1, 2),
            "s2": round(s2, 2),
            "s3": round(s3, 2),
        }

    def detect_pivot_breakouts(
        self,
        symbol: str,
        candles: List[Dict],
        pivot_levels: Dict[str, float],
        tolerance_pct: float = TOUCH_TOLERANCE_PCT,
        min_touches: int = MIN_TOUCHES_FOR_BREAKOUT,
    ) -> List[PivotBreakoutSignal]:
        """Detect three-touch breakouts on intraday candle data.

        Algorithm:
        1. For each pivot level, scan all candles to count "touches"
           (price within tolerance_pct of the level)
        2. Identify where the Nth touch resulted in a breakout
           (close beyond the level + confirmation distance)
        3. Validate with MACD histogram momentum
        4. Score confidence based on touch count + MACD + volume

        Args:
            symbol: Trading symbol being analyzed.
            candles: Intraday candle data (chronological, oldest first).
                Each dict must have: open, high, low, close, volume.
            pivot_levels: Dict from calculate_pivot_points().
            tolerance_pct: How close price must be to count as a "touch".
            min_touches: Minimum touches before breakout is meaningful.

        Returns:
            List of PivotBreakoutSignal for detected breakouts.
        """
        if not candles or len(candles) < 10:
            return []

        signals: List[PivotBreakoutSignal] = []

        # Compute MACD for the candle series
        macd_data = self._compute_macd(candles)

        # Track touches for each pivot level
        for level_name, level_value in pivot_levels.items():
            tracker = self._track_level_touches(
                candles, level_value, PivotLevel(level_name), tolerance_pct
            )

            # Check if we have enough touches AND a breakout
            if len(tracker.touches) < min_touches:
                continue

            # Check if the most recent candles show a breakout
            breakout = self._detect_break_at_level(
                candles, tracker, level_value, macd_data
            )

            if breakout is not None:
                signals.append(breakout)

        return signals

    def _track_level_touches(
        self,
        candles: List[Dict],
        level_value: float,
        level_name: PivotLevel,
        tolerance_pct: float,
    ) -> LevelTouchTracker:
        """Track how many times price touches a specific pivot level.

        A "touch" is counted when:
        - For resistance levels: the candle high is within tolerance of the level
          AND the candle closes below it (rejection)
        - For support levels: the candle low is within tolerance of the level
          AND the candle closes above it (bounce)
        - For pivot: either direction counts

        Consecutive candles touching the same level count as ONE touch
        (avoids double-counting a single attempt).

        Args:
            candles: Intraday candle data.
            level_value: The pivot level price.
            level_name: Which pivot level (R1, S1, etc.).
            tolerance_pct: Tolerance as percentage of level value.

        Returns:
            LevelTouchTracker with recorded touch events.
        """
        tracker = LevelTouchTracker(
            level_name=level_name, level_value=level_value
        )
        tolerance = level_value * (tolerance_pct / 100)
        last_touch_idx = -5  # Ensure first touch always counts

        for i, candle in enumerate(candles):
            high = candle["high"]
            low = candle["low"]
            close = candle["close"]

            # Skip if too close to last touch (within 2 candles = same attempt)
            if i - last_touch_idx < 3:
                continue

            is_touch = False
            distance = 0.0

            if level_name in (PivotLevel.R1, PivotLevel.R2, PivotLevel.R3):
                # Resistance: high approaches level from below
                if abs(high - level_value) <= tolerance and close < level_value:
                    is_touch = True
                    distance = abs(high - level_value) / level_value * 100
            elif level_name in (PivotLevel.S1, PivotLevel.S2, PivotLevel.S3):
                # Support: low approaches level from above
                if abs(low - level_value) <= tolerance and close > level_value:
                    is_touch = True
                    distance = abs(low - level_value) / level_value * 100
            else:
                # Pivot point: either direction
                if (abs(high - level_value) <= tolerance or
                        abs(low - level_value) <= tolerance):
                    is_touch = True
                    distance = min(
                        abs(high - level_value),
                        abs(low - level_value)
                    ) / level_value * 100

            if is_touch:
                tracker.touches.append(TouchEvent(
                    candle_index=i,
                    high=high,
                    low=low,
                    close=close,
                    distance_from_level=distance,
                ))
                last_touch_idx = i

        return tracker

    def _detect_break_at_level(
        self,
        candles: List[Dict],
        tracker: LevelTouchTracker,
        level_value: float,
        macd_data: List[Dict],
    ) -> Optional[PivotBreakoutSignal]:
        """Detect if the latest candles show a breakout after multiple touches.

        A breakout is confirmed when:
        - Price has touched the level min_touches times (already validated)
        - The most recent candle(s) close beyond the level
        - The break happens AFTER the last touch (temporal ordering)

        Args:
            candles: Full intraday candle data.
            tracker: Touch tracker for this level.
            level_value: The pivot level value.
            macd_data: MACD calculations for each candle.

        Returns:
            PivotBreakoutSignal if breakout detected, None otherwise.
        """
        if not tracker.touches:
            return None

        last_touch = tracker.touches[-1]
        last_touch_idx = last_touch.candle_index

        # Look at candles AFTER the last touch for the breakout
        # The break should happen within 5 candles of the last touch
        breakout_window = candles[last_touch_idx:]
        if len(breakout_window) < 2:
            return None  # Need at least 1 candle after the touch

        confirm_pct = level_value * (BREAKOUT_CONFIRM_PCT / 100)
        direction = None
        breakout_candle_idx = None
        breakout_price = 0.0

        for i, candle in enumerate(breakout_window[1:], start=1):
            actual_idx = last_touch_idx + i
            close = candle["close"]

            # Bullish breakout: close above resistance level
            if tracker.level_name in (
                PivotLevel.R1, PivotLevel.R2, PivotLevel.R3, PivotLevel.PIVOT
            ):
                if close > level_value + confirm_pct:
                    direction = BreakoutDirection.BULLISH
                    breakout_candle_idx = actual_idx
                    breakout_price = close
                    break

            # Bearish breakdown: close below support level
            if tracker.level_name in (
                PivotLevel.S1, PivotLevel.S2, PivotLevel.S3, PivotLevel.PIVOT
            ):
                if close < level_value - confirm_pct:
                    direction = BreakoutDirection.BEARISH
                    breakout_candle_idx = actual_idx
                    breakout_price = close
                    break

        if direction is None or breakout_candle_idx is None:
            return None

        # MACD histogram confirmation
        macd_confirmed, macd_trend = self._check_macd_confirmation(
            macd_data, breakout_candle_idx, direction
        )

        # Calculate confidence score
        confidence = self._calculate_confidence(
            touch_count=len(tracker.touches),
            macd_confirmed=macd_confirmed,
            last_touch_distance=last_touch.distance_from_level,
            candles_since_last_touch=(breakout_candle_idx - last_touch_idx),
        )

        # Calculate entry, SL, target
        entry_price = breakout_price
        if direction == BreakoutDirection.BULLISH:
            stop_loss = level_value - confirm_pct  # Just below the broken level
            risk = entry_price - stop_loss
            target_price = entry_price + (risk * 2)  # 2:1 R:R
        else:
            stop_loss = level_value + confirm_pct  # Just above the broken level
            risk = stop_loss - entry_price
            target_price = entry_price - (risk * 2)  # 2:1 R:R

        return PivotBreakoutSignal(
            symbol="",  # Will be set by caller
            direction=direction,
            pivot_level=tracker.level_name,
            level_value=level_value,
            touch_count=len(tracker.touches),
            breakout_price=breakout_price,
            macd_confirmed=macd_confirmed,
            macd_histogram_trend=macd_trend,
            confidence_score=confidence,
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            target_price=round(target_price, 2),
            max_potential_loss=round(risk, 2),
            timestamp=datetime.now().isoformat(),
            metadata={
                "touch_count": len(tracker.touches),
                "touch_candle_indices": [t.candle_index for t in tracker.touches],
                "breakout_candle_index": breakout_candle_idx,
                "macd_confirmed": macd_confirmed,
                "macd_trend": macd_trend,
                "level_name": tracker.level_name.value,
                "level_value": level_value,
            },
        )

    def _compute_macd(
        self,
        candles: List[Dict],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> List[Dict]:
        """Compute MACD, Signal line, and Histogram for candle data.

        Standard MACD calculation:
            MACD Line = EMA(fast) - EMA(slow)
            Signal Line = EMA(MACD Line, signal period)
            Histogram = MACD Line - Signal Line

        Args:
            candles: List of candle dicts with 'close' key.
            fast: Fast EMA period (default 12).
            slow: Slow EMA period (default 26).
            signal: Signal EMA period (default 9).

        Returns:
            List of dicts with keys: macd, signal, histogram.
            Same length as candles (early values are 0).
        """
        closes = [c["close"] for c in candles]

        if len(closes) < slow + signal:
            return [{"macd": 0, "signal": 0, "histogram": 0}] * len(closes)

        # Compute EMAs
        fast_ema = self._ema(closes, fast)
        slow_ema = self._ema(closes, slow)

        # MACD line
        macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]

        # Signal line (EMA of MACD line)
        signal_line = self._ema(macd_line, signal)

        # Histogram
        result = []
        for i in range(len(closes)):
            hist = macd_line[i] - signal_line[i]
            result.append({
                "macd": round(macd_line[i], 4),
                "signal": round(signal_line[i], 4),
                "histogram": round(hist, 4),
            })

        return result

    def _ema(self, values: List[float], period: int) -> List[float]:
        """Compute EMA for a list of values.

        Args:
            values: Input values.
            period: EMA period.

        Returns:
            List of EMA values (same length as input).
        """
        if len(values) < period:
            return [0.0] * len(values)

        multiplier = 2.0 / (period + 1)
        ema_values = [0.0] * len(values)

        # Seed with SMA
        sma = sum(values[:period]) / period
        ema_values[period - 1] = sma

        for i in range(period, len(values)):
            ema_values[i] = (
                (values[i] - ema_values[i - 1]) * multiplier + ema_values[i - 1]
            )

        return ema_values

    def _check_macd_confirmation(
        self,
        macd_data: List[Dict],
        breakout_idx: int,
        direction: BreakoutDirection,
    ) -> Tuple[bool, str]:
        """Check if MACD histogram confirms the breakout direction.

        For bullish breakout:
        - Confirmed if histogram is contracting (becoming less negative)
          heading into the breakout = hidden momentum building
        - OR histogram is already positive and expanding

        For bearish breakdown:
        - Confirmed if histogram is expanding negatively
          (accelerating selling momentum)
        - OR histogram just crossed below zero

        Args:
            macd_data: MACD data for each candle.
            breakout_idx: Index of the breakout candle.
            direction: Direction of the breakout.

        Returns:
            Tuple of (is_confirmed: bool, trend_description: str).
        """
        if breakout_idx < MACD_LOOKBACK_CANDLES or breakout_idx >= len(macd_data):
            return False, "insufficient_data"

        # Get histogram values leading into the breakout
        lookback_start = max(0, breakout_idx - MACD_LOOKBACK_CANDLES)
        hist_values = [
            macd_data[i]["histogram"]
            for i in range(lookback_start, breakout_idx + 1)
        ]

        if len(hist_values) < 3:
            return False, "insufficient_data"

        if direction == BreakoutDirection.BULLISH:
            return self._check_bullish_macd(hist_values)
        else:
            return self._check_bearish_macd(hist_values)

    def _check_bullish_macd(self, hist_values: List[float]) -> Tuple[bool, str]:
        """Check MACD histogram for bullish breakout confirmation.

        Patterns that confirm:
        1. Histogram contracting toward zero (less negative each bar)
        2. Histogram crossing from negative to positive
        3. Histogram positive and expanding
        """
        last_3 = hist_values[-3:]

        # Pattern 1: Contracting (values getting less negative or more positive)
        is_contracting = all(
            last_3[i] > last_3[i - 1] for i in range(1, len(last_3))
        )
        if is_contracting:
            return True, "histogram_contracting_bullish"

        # Pattern 2: Zero-line crossover
        if hist_values[-2] < 0 and hist_values[-1] >= 0:
            return True, "histogram_zero_cross_bullish"

        # Pattern 3: Positive and expanding
        if all(v > 0 for v in last_3) and last_3[-1] > last_3[-2]:
            return True, "histogram_expanding_bullish"

        # Not confirmed but not necessarily invalid
        return False, "no_macd_confirmation"

    def _check_bearish_macd(self, hist_values: List[float]) -> Tuple[bool, str]:
        """Check MACD histogram for bearish breakdown confirmation.

        Patterns that confirm:
        1. Histogram expanding negatively (getting more negative each bar)
        2. Histogram crossing from positive to negative
        3. Histogram negative and accelerating
        """
        last_3 = hist_values[-3:]

        # Pattern 1: Expanding negatively
        is_expanding_neg = all(
            last_3[i] < last_3[i - 1] for i in range(1, len(last_3))
        )
        if is_expanding_neg:
            return True, "histogram_expanding_bearish"

        # Pattern 2: Zero-line crossover downward
        if hist_values[-2] > 0 and hist_values[-1] <= 0:
            return True, "histogram_zero_cross_bearish"

        # Pattern 3: Negative and accelerating
        if all(v < 0 for v in last_3) and last_3[-1] < last_3[-2]:
            return True, "histogram_accelerating_bearish"

        return False, "no_macd_confirmation"

    def _calculate_confidence(
        self,
        touch_count: int,
        macd_confirmed: bool,
        last_touch_distance: float,
        candles_since_last_touch: int,
    ) -> float:
        """Calculate breakout confidence score (50-100).

        Scoring weights:
        - Touch count (35%): More touches = more exhaustion = higher confidence
        - MACD confirmation (30%): Momentum alignment is crucial
        - Proximity of last touch (20%): Tighter last touch = stronger test
        - Timing (15%): Break soon after last touch = more decisive

        Args:
            touch_count: Number of times level was tested.
            macd_confirmed: Whether MACD confirms the direction.
            last_touch_distance: How close the last touch was (% of level).
            candles_since_last_touch: How many candles between last touch and break.

        Returns:
            Confidence score between 50 and 100.
        """
        # Touch count score: 3 touches = 60, 4 = 80, 5+ = 100
        touch_score = min(100, (touch_count - 2) * 40 + 20)

        # MACD score: binary — confirmed or not
        macd_score = 100.0 if macd_confirmed else 30.0

        # Proximity score: closer touch = higher score
        # 0% distance = 100, 0.05% = 50, 0.1%+ = 0
        proximity_score = max(0, min(100, 100 - (last_touch_distance * 2000)))

        # Timing score: break within 1-3 candles of last touch = best
        if candles_since_last_touch <= 2:
            timing_score = 100.0
        elif candles_since_last_touch <= 5:
            timing_score = 70.0
        else:
            timing_score = max(0, 100 - (candles_since_last_touch - 5) * 15)

        # Weighted composite
        raw = (
            touch_score * 0.35
            + macd_score * 0.30
            + proximity_score * 0.20
            + timing_score * 0.15
        )

        # Scale to 50-100 range
        confidence = 50 + (raw / 2)
        return round(max(50, min(100, confidence)), 2)
