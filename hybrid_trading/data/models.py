"""
Core data models for tick data and candles.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Tick:
    """Represents a single tick of market data."""
    timestamp: datetime
    symbol: str
    last_price: float
    volume: int
    
    def __post_init__(self):
        """Validate tick data."""
        if self.last_price <= 0:
            raise ValueError(f"Invalid last_price: {self.last_price}")
        if self.volume < 0:
            raise ValueError(f"Invalid volume: {self.volume}")


@dataclass
class Candle:
    """Represents an OHLC candle for a specific timeframe."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    timeframe: str
    
    def __post_init__(self):
        """Validate candle data."""
        if self.high < self.low:
            raise ValueError(f"High ({self.high}) cannot be less than low ({self.low})")
        if self.open < 0 or self.high < 0 or self.low < 0 or self.close < 0:
            raise ValueError("Price values cannot be negative")
        if self.volume < 0:
            raise ValueError(f"Invalid volume: {self.volume}")
        if not self.timeframe:
            raise ValueError("Timeframe cannot be empty")
    
    @property
    def body_size(self) -> float:
        """Calculate the size of the candle body."""
        return abs(self.close - self.open)
    
    @property
    def range_size(self) -> float:
        """Calculate the total range of the candle."""
        return self.high - self.low
    
    @property
    def is_bullish(self) -> bool:
        """Check if candle is bullish (close > open)."""
        return self.close > self.open
    
    @property
    def is_bearish(self) -> bool:
        """Check if candle is bearish (close < open)."""
        return self.close < self.open
