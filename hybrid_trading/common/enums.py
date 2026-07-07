"""
Enumerations used throughout the hybrid trading system.
"""

from enum import Enum


class TrendState(Enum):
    """Market trend state classification."""
    UPTREND = "uptrend"
    DOWNTREND = "downtrend"
    NEUTRAL = "neutral"
    
    def __str__(self):
        return self.value


class MRState(Enum):
    """Mean reversion state classification."""
    EXTENDED_UP = "extended_up"
    EXTENDED_DOWN = "extended_down"
    NORMAL = "normal"
    
    def __str__(self):
        return self.value


class SignalType(Enum):
    """Trading signal types."""
    ENTRY_LONG = "entry_long"
    ENTRY_SHORT = "entry_short"
    EXIT_PARTIAL = "exit_partial"
    EXIT_FULL = "exit_full"
    
    def __str__(self):
        return self.value
    
    @property
    def is_entry(self) -> bool:
        """Check if signal is an entry signal."""
        return self in (SignalType.ENTRY_LONG, SignalType.ENTRY_SHORT)
    
    @property
    def is_exit(self) -> bool:
        """Check if signal is an exit signal."""
        return self in (SignalType.EXIT_PARTIAL, SignalType.EXIT_FULL)
    
    @property
    def is_long(self) -> bool:
        """Check if signal is for long direction."""
        return self == SignalType.ENTRY_LONG
    
    @property
    def is_short(self) -> bool:
        """Check if signal is for short direction."""
        return self == SignalType.ENTRY_SHORT
