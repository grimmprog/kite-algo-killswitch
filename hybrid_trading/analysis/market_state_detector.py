"""
Market State Detector for analyzing price structure and determining trend/MR states.
"""

from typing import List, Optional, Tuple
from datetime import datetime

from ..data.models import Candle
from ..data.candle_builder import CandleBuilder
from ..data.indicator_service import IndicatorService
from ..common.enums import TrendState, MRState


class MarketStateDetector:
    """
    Analyzes price structure to determine trend state and mean reversion state.
    
    Uses structure-based analysis (HH/HL/LH/LL patterns) rather than indicators alone.
    Indicators like EMA serve only as structural references, never as standalone signals.
    """
    
    def __init__(self, candle_builder: CandleBuilder, indicator_service: IndicatorService):
        """
        Initialize MarketStateDetector.
        
        Args:
            candle_builder: CandleBuilder instance for retrieving candle data
            indicator_service: IndicatorService for calculating indicators
        """
        self.candle_builder = candle_builder
        self.indicator_service = indicator_service
    
    def detect_trend_state(self, timeframe: str = '15m') -> TrendState:
        """
        Detect trend state on specified timeframe using structure analysis.
        
        UPTREND: Higher highs AND higher lows AND close above 20-EMA AND no structure break in last 3 candles
        DOWNTREND: Lower highs AND lower lows AND close below 20-EMA
        NEUTRAL: Neither UPTREND nor DOWNTREND conditions met
        
        Args:
            timeframe: Timeframe to analyze (default: '15m')
        
        Returns:
            TrendState (UPTREND, DOWNTREND, or NEUTRAL)
        """
        # Get sufficient candles for structure analysis
        candles = self.candle_builder.get_candles(timeframe, 50)
        
        if len(candles) < 10:
            # Insufficient data
            return TrendState.NEUTRAL
        
        # Get recent 3 candles for structure break check
        recent_candles = candles[-3:]
        
        # Identify swing points
        swing_highs = self._find_swing_highs(candles)
        swing_lows = self._find_swing_lows(candles)
        
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            # Insufficient swing points
            return TrendState.NEUTRAL
        
        # Check for higher highs and higher lows
        has_higher_highs = swing_highs[-1] > swing_highs[-2]
        has_higher_lows = swing_lows[-1] > swing_lows[-2]
        
        # Check for lower highs and lower lows
        has_lower_highs = swing_highs[-1] < swing_highs[-2]
        has_lower_lows = swing_lows[-1] < swing_lows[-2]
        
        # Calculate EMA as structural reference
        ema_20 = self.indicator_service.calculate_ema(timeframe, period=20)
        
        if ema_20 is None:
            # Insufficient data for EMA
            return TrendState.NEUTRAL
        
        # Check EMA position
        current_close = candles[-1].close
        close_above_ema = current_close > ema_20
        close_below_ema = current_close < ema_20
        
        # Check for structure break in last 3 candles
        structure_broken = any(self.detect_structure_break(timeframe, candle_idx=len(candles) - 3 + i) 
                              for i in range(3))
        
        # Determine trend state
        if has_higher_highs and has_higher_lows and close_above_ema and not structure_broken:
            return TrendState.UPTREND
        
        if has_lower_highs and has_lower_lows and close_below_ema:
            return TrendState.DOWNTREND
        
        return TrendState.NEUTRAL
    
    def _find_swing_highs(self, candles: List[Candle], lookback: int = 3) -> List[float]:
        """
        Identify swing high points in candle sequence.
        
        A swing high is a local maximum - a candle whose high is higher than
        the highs of 'lookback' candles before and after it.
        
        Args:
            candles: List of candles
            lookback: Number of candles to check on each side (default: 3)
        
        Returns:
            List of swing high prices
        """
        if len(candles) < lookback * 2 + 1:
            return []
        
        swing_highs = []
        
        for i in range(lookback, len(candles) - lookback):
            current_high = candles[i].high
            
            # Check if current high is higher than surrounding candles
            is_swing_high = True
            
            # Check candles before
            for j in range(i - lookback, i):
                if candles[j].high > current_high:
                    is_swing_high = False
                    break
            
            # Check candles after
            if is_swing_high:
                for j in range(i + 1, i + lookback + 1):
                    if candles[j].high > current_high:
                        is_swing_high = False
                        break
            
            if is_swing_high:
                swing_highs.append(current_high)
        
        return swing_highs
    
    def _find_swing_lows(self, candles: List[Candle], lookback: int = 3) -> List[float]:
        """
        Identify swing low points in candle sequence.
        
        A swing low is a local minimum - a candle whose low is lower than
        the lows of 'lookback' candles before and after it.
        
        Args:
            candles: List of candles
            lookback: Number of candles to check on each side (default: 3)
        
        Returns:
            List of swing low prices
        """
        if len(candles) < lookback * 2 + 1:
            return []
        
        swing_lows = []
        
        for i in range(lookback, len(candles) - lookback):
            current_low = candles[i].low
            
            # Check if current low is lower than surrounding candles
            is_swing_low = True
            
            # Check candles before
            for j in range(i - lookback, i):
                if candles[j].low < current_low:
                    is_swing_low = False
                    break
            
            # Check candles after
            if is_swing_low:
                for j in range(i + 1, i + lookback + 1):
                    if candles[j].low < current_low:
                        is_swing_low = False
                        break
            
            if is_swing_low:
                swing_lows.append(current_low)
        
        return swing_lows
    
    def detect_structure_break(self, timeframe: str, candle_idx: Optional[int] = None) -> bool:
        """
        Detect if structure has been broken at a specific candle.
        
        Structure break occurs when:
        - In uptrend: Price breaks below previous higher low
        - In downtrend: Price breaks above previous lower high
        
        Args:
            timeframe: Timeframe to analyze
            candle_idx: Index of candle to check (None = latest candle)
        
        Returns:
            True if structure broken, False otherwise
        """
        candles = self.candle_builder.get_candles(timeframe, 50)
        
        if len(candles) < 10:
            return False
        
        # Use latest candle if index not specified
        if candle_idx is None:
            candle_idx = len(candles) - 1
        
        # Ensure valid index
        if candle_idx < 0 or candle_idx >= len(candles):
            return False
        
        # Get candles up to the specified index
        candles_subset = candles[:candle_idx + 1]
        
        if len(candles_subset) < 10:
            return False
        
        # Identify swing points
        swing_highs = self._find_swing_highs(candles_subset)
        swing_lows = self._find_swing_lows(candles_subset)
        
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return False
        
        # Check for structure break
        current_candle = candles_subset[-1]
        
        # Check if in uptrend (higher highs and higher lows)
        if swing_highs[-1] > swing_highs[-2] and swing_lows[-1] > swing_lows[-2]:
            # In uptrend: structure breaks if price goes below previous higher low
            previous_hl = swing_lows[-2]
            if current_candle.low < previous_hl:
                return True
        
        # Check if in downtrend (lower highs and lower lows)
        if swing_highs[-1] < swing_highs[-2] and swing_lows[-1] < swing_lows[-2]:
            # In downtrend: structure breaks if price goes above previous lower high
            previous_lh = swing_highs[-2]
            if current_candle.high > previous_lh:
                return True
        
        return False
    
    def detect_mr_state(self, timeframe: str = '5m') -> MRState:
        """
        Detect mean reversion state on specified timeframe.
        
        EXTENDED_UP: Impulse exceeds 1.5x recent average OR 3+ consecutive large candles OR distance from VWAP > 1.2x ATR
        EXTENDED_DOWN: Same logic but in opposite direction
        NORMAL: Neither extended condition met
        
        Args:
            timeframe: Timeframe to analyze (default: '5m')
        
        Returns:
            MRState (EXTENDED_UP, EXTENDED_DOWN, or NORMAL)
        """
        # Get candles for analysis
        candles = self.candle_builder.get_candles(timeframe, 20)
        
        if len(candles) < 10:
            # Insufficient data
            return MRState.NORMAL
        
        # Calculate recent impulse average (last 10 candles)
        recent_candles = candles[-10:]
        impulses = []
        
        # Calculate impulse sizes for recent candles
        for i in range(len(recent_candles) - 1):
            impulse = abs(recent_candles[i + 1].close - recent_candles[i].close)
            impulses.append(impulse)
        
        if not impulses:
            return MRState.NORMAL
        
        avg_impulse = sum(impulses) / len(impulses)
        
        # Calculate current impulse (last 3 candles)
        if len(candles) >= 3:
            current_impulse = abs(candles[-1].close - candles[-3].open)
        else:
            current_impulse = 0.0
        
        # Check condition 1: Impulse extended
        impulse_extended = current_impulse > 1.5 * avg_impulse
        
        # Check condition 2: Consecutive large candles
        consecutive_large = self.indicator_service.count_consecutive_large_candles(candles[-3:]) >= 3
        
        # Check condition 3: Distance from VWAP
        vwap = self.indicator_service.calculate_vwap(timeframe, lookback=20)
        atr = self.indicator_service.calculate_atr(timeframe, period=14)
        
        vwap_extended = False
        if vwap is not None and atr is not None and atr > 0:
            distance_from_vwap = abs(candles[-1].close - vwap)
            vwap_extended = distance_from_vwap > 1.2 * atr
        
        # Determine if extended
        is_extended = impulse_extended or consecutive_large or vwap_extended
        
        if not is_extended:
            return MRState.NORMAL
        
        # Determine direction
        if vwap is not None:
            if candles[-1].close > vwap:
                return MRState.EXTENDED_UP
            else:
                return MRState.EXTENDED_DOWN
        else:
            # Fallback: use price direction
            if candles[-1].close > candles[0].close:
                return MRState.EXTENDED_UP
            else:
                return MRState.EXTENDED_DOWN
    
    def is_vertical_extension(self, timeframe: str, body_threshold: float = 2.0, distance_threshold: float = 2.0) -> bool:
        """
        Check if current move is a vertical extension (impulse with little/no pullback).
        
        Vertical extension occurs when:
        - Candle body size exceeds recent average by threshold (default: 2x)
        - Distance from last structure point exceeds ATR threshold (default: 2x)
        
        Args:
            timeframe: Timeframe to analyze
            body_threshold: Multiplier for average body size (default: 2.0)
            distance_threshold: Multiplier for ATR (default: 2.0)
        
        Returns:
            True if vertical extension detected, False otherwise
        """
        candles = self.candle_builder.get_candles(timeframe, 20)
        
        if len(candles) < 10:
            return False
        
        # Calculate average body size
        avg_body = self.indicator_service.calculate_average_body_size(candles[:-1])
        
        if avg_body == 0:
            return False
        
        # Check if current candle body exceeds threshold
        current_body = candles[-1].body_size
        body_extended = current_body > body_threshold * avg_body
        
        # Calculate ATR
        atr = self.indicator_service.calculate_atr(timeframe, period=14)
        
        if atr is None or atr == 0:
            return body_extended
        
        # Find last structure level
        structure_level = self.find_structure_level(timeframe, direction='up' if candles[-1].is_bullish else 'down')
        
        if structure_level is None:
            return body_extended
        
        # Check distance from structure
        distance = abs(candles[-1].close - structure_level)
        distance_extended = distance > distance_threshold * atr
        
        return body_extended and distance_extended
    
    def find_structure_level(self, timeframe: str, direction: str) -> Optional[float]:
        """
        Find previous structure level (HL for uptrend, LH for downtrend).
        
        Args:
            timeframe: Timeframe to analyze
            direction: 'up' for uptrend (find HL), 'down' for downtrend (find LH)
        
        Returns:
            Structure level price or None if not found
        """
        candles = self.candle_builder.get_candles(timeframe, 50)
        
        if len(candles) < 10:
            return None
        
        if direction == 'up':
            # Find previous higher low
            swing_lows = self._find_swing_lows(candles)
            if len(swing_lows) >= 2:
                return swing_lows[-2]  # Previous higher low
        
        elif direction == 'down':
            # Find previous lower high
            swing_highs = self._find_swing_highs(candles)
            if len(swing_highs) >= 2:
                return swing_highs[-2]  # Previous lower high
        
        return None
    
    def detect_trend_weakening(self, timeframe: str, direction: str, 
                              failure_candles: int = 5, 
                              reduced_range_count: int = 3) -> bool:
        """
        Detect trend weakening conditions.
        
        Trend weakening occurs when ANY of these conditions are met:
        1. Failure to make new HH/LL after N candles (default: 5)
        2. N consecutive candles with reduced range (default: 3)
        3. Close below/above previous impulse midpoint
        
        Args:
            timeframe: Timeframe to analyze
            direction: 'up' for uptrend, 'down' for downtrend
            failure_candles: Number of candles to check for HH/LL failure (default: 5)
            reduced_range_count: Number of consecutive reduced range candles (default: 3)
        
        Returns:
            True if trend weakening detected, False otherwise
        """
        candles = self.candle_builder.get_candles(timeframe, 50)
        
        if len(candles) < failure_candles + 5:
            return False
        
        # Condition 1: Failure to make new HH/LL after N candles
        recent_candles = candles[-failure_candles:]
        
        if direction == 'up':
            # Check if no new higher high in recent candles
            previous_high = max(c.high for c in candles[:-failure_candles])
            recent_high = max(c.high for c in recent_candles)
            
            if recent_high <= previous_high:
                return True
        
        elif direction == 'down':
            # Check if no new lower low in recent candles
            previous_low = min(c.low for c in candles[:-failure_candles])
            recent_low = min(c.low for c in recent_candles)
            
            if recent_low >= previous_low:
                return True
        
        # Condition 2: Consecutive candles with reduced range
        if len(candles) >= reduced_range_count + 1:
            # Calculate average range of earlier candles
            earlier_candles = candles[:-reduced_range_count]
            avg_range = self.indicator_service.calculate_average_range(earlier_candles)
            
            if avg_range > 0:
                # Check if last N candles have reduced range
                reduced_count = 0
                for candle in candles[-reduced_range_count:]:
                    if candle.range_size < avg_range:
                        reduced_count += 1
                
                if reduced_count >= reduced_range_count:
                    return True
        
        # Condition 3: Close below/above impulse midpoint
        # Find the last impulse leg (last 5-10 candles)
        impulse_candles = candles[-10:]
        
        if len(impulse_candles) >= 2:
            impulse_start = impulse_candles[0].open
            impulse_end = impulse_candles[-2].close  # Previous candle
            impulse_midpoint = (impulse_start + impulse_end) / 2.0
            
            current_close = candles[-1].close
            
            if direction == 'up':
                # In uptrend, close below midpoint is weakening
                if current_close < impulse_midpoint:
                    return True
            
            elif direction == 'down':
                # In downtrend, close above midpoint is weakening
                if current_close > impulse_midpoint:
                    return True
        
        return False
