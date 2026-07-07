"""Scanner Service for trend-pullback and consolidation-breakout market scans.

Implements Requirements: 1.1, 2.2, 2.3

Provides pure logic for:
- Trend-pullback scanning with EMA-based pullback detection and confidence scoring
- Consolidation detection on candle data (high-low spread < 15% avg price over 6+ candles)
- Breakout detection (price > 10% above consolidation range high)
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ScanType(str, Enum):
    """Types of market scans supported."""

    TREND_PULLBACK = "trend_pullback"
    CONSOLIDATION_BREAKOUT = "consolidation_breakout"


class ScanSignal(BaseModel):
    """A scored trading signal produced by the scanner.

    Attributes:
        symbol: Trading symbol (e.g., "RELIANCE", "NIFTY24600CE").
        scan_type: Type of scan that generated this signal.
        confidence_score: Signal strength score between 50 and 100.
        entry_price: Suggested entry price.
        stop_loss: Suggested stop-loss price.
        target_price: Suggested target price.
        max_potential_loss: Maximum loss if stop-loss is hit (entry - SL).
        timestamp: ISO timestamp of when the signal was generated.
        metadata: Additional context (trend direction, volume ratio, etc.).
    """

    symbol: str
    scan_type: ScanType
    confidence_score: float = Field(ge=50, le=100)
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    target_price: float = Field(gt=0)
    max_potential_loss: float
    timestamp: str
    metadata: Dict = Field(default_factory=dict)


class ConsolidationPattern(BaseModel):
    """A detected consolidation pattern on candle data.

    Consolidation is identified when the high-low spread is less than
    15% of the average price over a minimum of 6 consecutive candles.

    Attributes:
        symbol: Trading symbol being analyzed.
        range_high: Highest high in the consolidation range.
        range_low: Lowest low in the consolidation range.
        avg_price: Average price across consolidation candles.
        candle_count: Number of candles in the consolidation.
        duration_minutes: Duration of consolidation in minutes.
        is_breakout: Whether a breakout has been detected.
        breakout_price: Price at which breakout occurred (if any).
    """

    symbol: str
    range_high: float
    range_low: float
    avg_price: float
    candle_count: int = Field(ge=6)
    duration_minutes: int = Field(ge=0)
    is_breakout: bool = False
    breakout_price: Optional[float] = None


class ScannerService:
    """Orchestrates market scanning logic for trend-pullback and consolidation-breakout.

    This service contains pure computational logic — no external API calls.
    Candle data is passed in by the caller (worker or API router).

    Methods:
        run_trend_pullback_scan: Scan watchlist for trend-pullback setups.
        detect_consolidation: Detect tight-range consolidation on candles.
        check_breakout: Check if price broke above consolidation range.
    """

    def run_trend_pullback_scan(
        self,
        watchlist: List[str],
        candle_data_by_symbol: Dict[str, List[Dict]],
    ) -> List[ScanSignal]:
        """Run trend-pullback scan for all symbols in watchlist.

        For each symbol, calculates EMA20, detects if price has pulled back
        to the EMA and bounced. Scores based on:
        - Distance from EMA (weight 30%): closer = better pullback
        - Volume confirmation (weight 30%): above-average volume on bounce
        - Trend strength / momentum (weight 40%): ADX-like directional movement

        Only signals with confidence >= 50 are returned.

        Requirements covered:
        - 1.1: Trigger backend trend-pullback scan for all symbols in watchlist

        Args:
            watchlist: List of symbol names to scan.
            candle_data_by_symbol: Dict mapping symbol -> list of candle dicts.
                Each candle dict must have: open, high, low, close, volume.

        Returns:
            List of ScanSignal objects for symbols meeting the threshold.
        """
        signals: List[ScanSignal] = []

        for symbol in watchlist:
            candles = candle_data_by_symbol.get(symbol)
            if not candles or len(candles) < 20:
                logger.debug(
                    "Skipping %s: insufficient candle data (%d candles)",
                    symbol,
                    len(candles) if candles else 0,
                )
                continue

            signal = self._analyze_trend_pullback(symbol, candles)
            if signal is not None:
                signals.append(signal)

        logger.info(
            "Trend pullback scan complete: %d signals from %d symbols",
            len(signals),
            len(watchlist),
        )
        return signals

    def detect_consolidation(
        self, symbol: str, candles: List[Dict]
    ) -> Optional[ConsolidationPattern]:
        """Detect tight-range consolidation on candle data.

        Consolidation is identified when:
        - The high-low spread (max_high - min_low) is less than 15% of avg price
        - This condition holds over at least 6 consecutive candles

        Scans from the most recent candles backwards to find the longest
        active consolidation range.

        Requirements covered:
        - 2.2: Identify consolidation as range where high-low spread < 15% avg price
               over minimum of 6 consecutive 3-minute candles

        Args:
            symbol: Trading symbol being analyzed.
            candles: List of candle dicts with keys: open, high, low, close, volume.
                     Expected in chronological order (oldest first).

        Returns:
            ConsolidationPattern if consolidation is detected, None otherwise.
        """
        if not candles or len(candles) < 6:
            return None

        # Work from the most recent candles and find the longest consolidation
        # starting from the end
        best_count = 0
        best_start_idx = -1

        # Try expanding the consolidation window from the end
        for start_idx in range(len(candles) - 6, -1, -1):
            window = candles[start_idx:]
            if self._is_consolidation(window):
                if len(window) > best_count:
                    best_count = len(window)
                    best_start_idx = start_idx
                break  # Found the longest window starting from this point

        # If no consolidation starting from the earliest point, try all windows
        # ending at the last candle
        if best_count == 0:
            for window_size in range(len(candles), 5, -1):
                window = candles[-window_size:]
                if self._is_consolidation(window):
                    best_count = window_size
                    best_start_idx = len(candles) - window_size
                    break

        if best_count < 6:
            return None

        consolidation_candles = candles[best_start_idx: best_start_idx + best_count]

        highs = [c["high"] for c in consolidation_candles]
        lows = [c["low"] for c in consolidation_candles]
        closes = [c["close"] for c in consolidation_candles]

        range_high = max(highs)
        range_low = min(lows)
        avg_price = sum(closes) / len(closes)

        # Estimate duration: assume 3-minute candles by default
        duration_minutes = best_count * 3

        return ConsolidationPattern(
            symbol=symbol,
            range_high=range_high,
            range_low=range_low,
            avg_price=avg_price,
            candle_count=best_count,
            duration_minutes=duration_minutes,
            is_breakout=False,
            breakout_price=None,
        )

    def check_breakout(
        self, pattern: ConsolidationPattern, current_price: float
    ) -> bool:
        """Check if price has broken out above the consolidation range.

        A breakout is confirmed when the current price is more than 10%
        above the consolidation range high.

        Requirements covered:
        - 2.3: Highlight breakout signal when price moves more than 10% above
               the consolidation range high

        Args:
            pattern: The detected ConsolidationPattern.
            current_price: Current market price of the symbol.

        Returns:
            True if current_price > pattern.range_high * 1.10, False otherwise.
        """
        breakout_threshold = pattern.range_high * 1.10
        return current_price > breakout_threshold

    # --- Private helper methods ---

    def _analyze_trend_pullback(
        self, symbol: str, candles: List[Dict]
    ) -> Optional[ScanSignal]:
        """Analyze a single symbol for trend-pullback setup.

        Logic:
        1. Compute EMA20 on close prices
        2. Check if price is in an uptrend (close > EMA20 for most of last 10 candles)
        3. Detect pullback: price dipped near/below EMA then bounced
        4. Score: distance_score(30%) + volume_score(30%) + momentum_score(40%)

        Args:
            symbol: Symbol being analyzed.
            candles: List of candle dicts (chronological, oldest first).

        Returns:
            ScanSignal if setup qualifies (confidence >= 50), None otherwise.
        """
        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        volumes = [c["volume"] for c in candles]

        # Compute EMA20
        ema20 = self._compute_ema(closes, period=20)
        if not ema20 or len(ema20) < 5:
            return None

        current_close = closes[-1]
        current_ema = ema20[-1]

        # Check uptrend: price above EMA for at least 60% of last 10 candles
        recent_closes = closes[-10:]
        recent_ema = ema20[-10:]
        above_ema_count = sum(
            1 for c, e in zip(recent_closes, recent_ema) if c > e
        )
        if above_ema_count < 6:
            return None  # Not in a clear uptrend

        # Detect pullback: price touched or dipped below EMA in last 5 candles
        # then bounced back above
        pullback_detected = False
        pullback_low = current_close
        for i in range(-5, -1):
            low = lows[i]
            ema_at_point = ema20[i]
            if low <= ema_at_point * 1.02:  # Within 2% of EMA or below
                pullback_detected = True
                pullback_low = min(pullback_low, low)

        if not pullback_detected:
            return None

        # Current price must be back above EMA (bounce confirmed)
        if current_close <= current_ema:
            return None

        # --- Scoring ---

        # 1. Distance from EMA score (30%): closer to EMA = better entry
        # Normalize: 0% distance = 100, 5%+ distance = 0
        distance_pct = abs(current_close - current_ema) / current_ema * 100
        distance_score = max(0, min(100, 100 - (distance_pct * 20)))

        # 2. Volume confirmation score (30%): current volume vs average
        avg_volume = sum(volumes[-20:]) / len(volumes[-20:]) if volumes[-20:] else 1
        current_volume = volumes[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        # Ratio 1.5+ = 100, ratio 0.5 = 0
        volume_score = max(0, min(100, (volume_ratio - 0.5) * 100))

        # 3. Trend strength / momentum score (40%): ADX-like directional movement
        momentum_score = self._compute_momentum_score(closes, highs, lows)

        # Weighted composite
        raw_confidence = (
            distance_score * 0.30
            + volume_score * 0.30
            + momentum_score * 0.40
        )

        # Map to 50-100 range: raw_confidence [0,100] → [50,100]
        confidence = 50 + (raw_confidence / 2)
        confidence = max(50, min(100, confidence))

        # Only emit signal if there's meaningful confidence
        if raw_confidence < 1:
            return None

        # Calculate entry, SL, target
        entry_price = current_close
        stop_loss = pullback_low * 0.99  # 1% below pullback low
        risk = entry_price - stop_loss
        target_price = entry_price + (risk * 2)  # 2:1 reward:risk
        max_potential_loss = risk

        return ScanSignal(
            symbol=symbol,
            scan_type=ScanType.TREND_PULLBACK,
            confidence_score=round(confidence, 2),
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            target_price=round(target_price, 2),
            max_potential_loss=round(max_potential_loss, 2),
            timestamp=datetime.now().isoformat(),
            metadata={
                "ema20": round(current_ema, 2),
                "distance_pct": round(distance_pct, 2),
                "volume_ratio": round(volume_ratio, 2),
                "distance_score": round(distance_score, 2),
                "volume_score": round(volume_score, 2),
                "momentum_score": round(momentum_score, 2),
                "trend_direction": "bullish",
            },
        )

    def _compute_ema(self, values: List[float], period: int) -> List[float]:
        """Compute Exponential Moving Average for a list of values.

        Uses the standard EMA formula:
            multiplier = 2 / (period + 1)
            EMA_today = (value - EMA_yesterday) * multiplier + EMA_yesterday

        The first EMA value is seeded with a simple moving average (SMA)
        of the first `period` values.

        Args:
            values: List of numeric values (e.g., close prices).
            period: EMA period (e.g., 20).

        Returns:
            List of EMA values, same length as input values.
            Returns empty list if input has fewer values than period.
        """
        if len(values) < period:
            return []

        multiplier = 2 / (period + 1)

        # Seed with SMA of first `period` values
        sma = sum(values[:period]) / period
        ema_values = [0.0] * (period - 1) + [sma]

        # Compute EMA for remaining values
        for i in range(period, len(values)):
            ema = (values[i] - ema_values[i - 1]) * multiplier + ema_values[i - 1]
            ema_values.append(ema)

        return ema_values

    def _compute_momentum_score(
        self, closes: List[float], highs: List[float], lows: List[float]
    ) -> float:
        """Compute a momentum score (0-100) based on directional movement.

        Uses a simplified ADX-like calculation:
        - Computes +DM and -DM (directional movement)
        - Smooths over 14 periods
        - Score based on ratio of +DM to total DM (bullish bias)

        Args:
            closes: Close prices.
            highs: High prices.
            lows: Low prices.

        Returns:
            Momentum score between 0 and 100.
        """
        if len(closes) < 15:
            return 50.0  # Neutral when insufficient data

        period = 14

        # Compute directional movements
        plus_dm_sum = 0.0
        minus_dm_sum = 0.0

        for i in range(-period, 0):
            high_diff = highs[i] - highs[i - 1]
            low_diff = lows[i - 1] - lows[i]

            plus_dm = high_diff if high_diff > low_diff and high_diff > 0 else 0
            minus_dm = low_diff if low_diff > high_diff and low_diff > 0 else 0

            plus_dm_sum += plus_dm
            minus_dm_sum += minus_dm

        total_dm = plus_dm_sum + minus_dm_sum
        if total_dm == 0:
            return 50.0  # No directional movement

        # Score: ratio of bullish DM to total DM, scaled to 0-100
        directional_ratio = plus_dm_sum / total_dm
        score = directional_ratio * 100

        return max(0, min(100, score))

    def _is_consolidation(self, candles: List[Dict]) -> bool:
        """Check if a set of candles form a consolidation pattern.

        A consolidation exists when:
        (max_high - min_low) / avg_price < 0.15

        Args:
            candles: List of candle dicts with high, low, close keys.

        Returns:
            True if the spread condition is met, False otherwise.
        """
        if len(candles) < 6:
            return False

        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]

        max_high = max(highs)
        min_low = min(lows)
        avg_price = sum(closes) / len(closes)

        if avg_price == 0:
            return False

        spread_ratio = (max_high - min_low) / avg_price
        return spread_ratio < 0.15
