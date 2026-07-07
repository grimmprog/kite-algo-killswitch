"""
Indicator Service for calculating technical indicators from candle data.
"""

from typing import List, Optional
import math

from .models import Candle
from .candle_builder import CandleBuilder


class IndicatorService:
    """
    Service for calculating technical indicators from candle data.
    
    All indicators are calculated using standard formulas and operate on
    futures data (not spot index data).
    """
    
    def __init__(self, candle_builder: CandleBuilder):
        """
        Initialize IndicatorService with a CandleBuilder.
        
        Args:
            candle_builder: CandleBuilder instance to retrieve candle data from
        """
        self.candle_builder = candle_builder
    
    def calculate_vwap(self, timeframe: str, lookback: int) -> Optional[float]:
        """
        Calculate Volume Weighted Average Price (VWAP) on futures data.
        
        VWAP = Sum(Price * Volume) / Sum(Volume)
        where Price = (High + Low + Close) / 3 (typical price)
        
        Args:
            timeframe: Timeframe string (e.g., '5m', '15m')
            lookback: Number of candles to include in calculation
        
        Returns:
            VWAP value or None if insufficient data
        """
        candles = self.candle_builder.get_candles(timeframe, lookback)
        
        if not candles:
            return None
        
        total_pv = 0.0  # Sum of (price * volume)
        total_volume = 0.0  # Sum of volume
        
        for candle in candles:
            # Typical price
            typical_price = (candle.high + candle.low + candle.close) / 3.0
            
            # Accumulate
            total_pv += typical_price * candle.volume
            total_volume += candle.volume
        
        # Avoid division by zero
        if total_volume == 0:
            return None
        
        vwap = total_pv / total_volume
        return vwap
    
    def calculate_atr(self, timeframe: str, period: int = 14) -> Optional[float]:
        """
        Calculate Average True Range (ATR) using standard formula.
        
        True Range (TR) = max(high - low, abs(high - prev_close), abs(low - prev_close))
        ATR = Simple Moving Average of TR over period
        
        Args:
            timeframe: Timeframe string (e.g., '5m', '15m')
            period: Number of periods for ATR calculation (default: 14)
        
        Returns:
            ATR value or None if insufficient data
        """
        # Need period + 1 candles (one extra for previous close)
        candles = self.candle_builder.get_candles(timeframe, period + 1)
        
        if len(candles) < period + 1:
            return None
        
        true_ranges = []
        
        # Calculate True Range for each candle (starting from index 1)
        for i in range(1, len(candles)):
            current = candles[i]
            previous = candles[i - 1]
            
            # Three components of True Range
            high_low = current.high - current.low
            high_prev_close = abs(current.high - previous.close)
            low_prev_close = abs(current.low - previous.close)
            
            # True Range is the maximum of the three
            tr = max(high_low, high_prev_close, low_prev_close)
            true_ranges.append(tr)
        
        # ATR is the simple moving average of True Ranges
        if not true_ranges:
            return None
        
        atr = sum(true_ranges) / len(true_ranges)
        return atr
    
    def calculate_ema(self, timeframe: str, period: int = 20) -> Optional[float]:
        """
        Calculate Exponential Moving Average (EMA) using standard formula.
        
        EMA = Price(t) * k + EMA(t-1) * (1 - k)
        where k = 2 / (period + 1)
        
        For the first EMA value, we use SMA as the seed.
        
        Args:
            timeframe: Timeframe string (e.g., '5m', '15m')
            period: Number of periods for EMA calculation (default: 20)
        
        Returns:
            EMA value or None if insufficient data
        """
        candles = self.candle_builder.get_candles(timeframe, period * 2)
        
        if len(candles) < period:
            return None
        
        # Calculate smoothing factor
        k = 2.0 / (period + 1)
        
        # Use SMA of first 'period' candles as seed
        sma = sum(c.close for c in candles[:period]) / period
        ema = sma
        
        # Calculate EMA for remaining candles
        for i in range(period, len(candles)):
            price = candles[i].close
            ema = price * k + ema * (1 - k)
        
        return ema
    
    def calculate_sma(self, timeframe: str, period: int) -> Optional[float]:
        """
        Calculate Simple Moving Average (SMA).
        
        SMA = Sum(Close prices) / period
        
        Args:
            timeframe: Timeframe string (e.g., '5m', '15m')
            period: Number of periods for SMA calculation
        
        Returns:
            SMA value or None if insufficient data
        """
        candles = self.candle_builder.get_candles(timeframe, period)
        
        if len(candles) < period:
            return None
        
        sma = sum(c.close for c in candles) / period
        return sma
    
    def get_recent_candles(self, timeframe: str, count: int) -> List[Candle]:
        """
        Get recent candles for custom calculations.
        
        Args:
            timeframe: Timeframe string
            count: Number of candles to retrieve
        
        Returns:
            List of recent candles
        """
        return self.candle_builder.get_candles(timeframe, count)
    
    def calculate_impulse_size(self, candles: List[Candle]) -> float:
        """
        Calculate the size of an impulse move.
        
        Impulse size = abs(last_close - first_open)
        
        Args:
            candles: List of candles representing the impulse
        
        Returns:
            Impulse size
        """
        if not candles:
            return 0.0
        
        return abs(candles[-1].close - candles[0].open)
    
    def calculate_average_body_size(self, candles: List[Candle]) -> float:
        """
        Calculate average candle body size.
        
        Args:
            candles: List of candles
        
        Returns:
            Average body size
        """
        if not candles:
            return 0.0
        
        total_body = sum(c.body_size for c in candles)
        return total_body / len(candles)
    
    def calculate_average_range(self, candles: List[Candle]) -> float:
        """
        Calculate average candle range (high - low).
        
        Args:
            candles: List of candles
        
        Returns:
            Average range
        """
        if not candles:
            return 0.0
        
        total_range = sum(c.range_size for c in candles)
        return total_range / len(candles)
    
    def count_consecutive_large_candles(self, candles: List[Candle], threshold_multiplier: float = 1.5) -> int:
        """
        Count consecutive large candles from the end of the list.
        
        A candle is considered "large" if its body size exceeds the average
        body size of all candles by the threshold multiplier.
        
        Args:
            candles: List of candles
            threshold_multiplier: Multiplier for average body size (default: 1.5)
        
        Returns:
            Number of consecutive large candles from the end
        """
        if not candles:
            return 0
        
        avg_body = self.calculate_average_body_size(candles)
        threshold = avg_body * threshold_multiplier
        
        count = 0
        # Count from the end backwards
        for candle in reversed(candles):
            if candle.body_size >= threshold:
                count += 1
            else:
                break
        
        return count
