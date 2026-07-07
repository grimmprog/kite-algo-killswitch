"""
Candle Builder for constructing OHLC candles from tick data across multiple timeframes.
"""

from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .models import Tick, Candle


class CandleBuilder:
    """
    Builds OHLC candles from tick data across multiple timeframes.
    
    Maintains current candles and historical candles for each timeframe.
    Detects candle completions and manages historical buffer.
    """
    
    # Timeframe to minutes mapping
    TIMEFRAME_MINUTES = {
        '1m': 1,
        '3m': 3,
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '1h': 60,
        '2h': 120,
        '4h': 240,
        '1d': 1440,
    }
    
    def __init__(self, timeframes: List[str], max_historical_candles: int = 50):
        """
        Initialize CandleBuilder with specified timeframes.
        
        Args:
            timeframes: List of timeframe strings (e.g., ['1m', '3m', '5m', '15m', '30m'])
            max_historical_candles: Maximum number of historical candles to maintain per timeframe
        
        Raises:
            ValueError: If any timeframe is not supported
        """
        # Validate timeframes
        for tf in timeframes:
            if tf not in self.TIMEFRAME_MINUTES:
                raise ValueError(f"Unsupported timeframe: {tf}. Supported: {list(self.TIMEFRAME_MINUTES.keys())}")
        
        self.timeframes = timeframes
        self.max_historical_candles = max_historical_candles
        
        # Current candles being built (timeframe -> Candle)
        self.current_candles: Dict[str, Optional[Candle]] = {tf: None for tf in timeframes}
        
        # Historical completed candles (timeframe -> deque of Candles)
        self.historical_candles: Dict[str, deque] = {
            tf: deque(maxlen=max_historical_candles) for tf in timeframes
        }
        
        # Track candle start times (timeframe -> datetime)
        self.candle_start_times: Dict[str, Optional[datetime]] = {tf: None for tf in timeframes}
    
    def on_tick(self, tick: Tick) -> Dict[str, Optional[Candle]]:
        """
        Process incoming tick and update candles for all timeframes.
        
        Args:
            tick: Incoming tick data
        
        Returns:
            Dict mapping timeframe to completed candle (None if candle not complete)
        """
        completed_candles = {}
        
        for timeframe in self.timeframes:
            completed_candle = self._update_candle(tick, timeframe)
            completed_candles[timeframe] = completed_candle
        
        return completed_candles
    
    def _update_candle(self, tick: Tick, timeframe: str) -> Optional[Candle]:
        """
        Update candle for a specific timeframe.
        
        Args:
            tick: Incoming tick data
            timeframe: Timeframe to update
        
        Returns:
            Completed candle if timeframe period ended, None otherwise
        """
        current_candle = self.current_candles[timeframe]
        candle_start = self.candle_start_times[timeframe]
        
        # Calculate candle boundaries
        candle_start_time = self._get_candle_start_time(tick.timestamp, timeframe)
        
        # Check if we need to finalize current candle and start new one
        if candle_start is not None and candle_start_time > candle_start:
            # Finalize current candle
            completed_candle = current_candle
            if completed_candle is not None:
                self.historical_candles[timeframe].append(completed_candle)
            
            # Start new candle
            self.current_candles[timeframe] = self._create_new_candle(tick, timeframe, candle_start_time)
            self.candle_start_times[timeframe] = candle_start_time
            
            return completed_candle
        
        # Initialize first candle if needed
        if current_candle is None:
            self.current_candles[timeframe] = self._create_new_candle(tick, timeframe, candle_start_time)
            self.candle_start_times[timeframe] = candle_start_time
            return None
        
        # Update existing candle
        self._update_existing_candle(current_candle, tick)
        
        return None
    
    def _get_candle_start_time(self, timestamp: datetime, timeframe: str) -> datetime:
        """
        Calculate the start time of the candle that contains the given timestamp.
        
        Args:
            timestamp: Tick timestamp
            timeframe: Timeframe string
        
        Returns:
            Start time of the candle period
        """
        minutes = self.TIMEFRAME_MINUTES[timeframe]
        
        # Round down to the nearest timeframe boundary
        # For example, for 5m timeframe:
        # 09:32:45 -> 09:30:00
        # 09:37:12 -> 09:35:00
        
        # Get total minutes since midnight
        total_minutes = timestamp.hour * 60 + timestamp.minute
        
        # Round down to nearest timeframe boundary
        candle_minutes = (total_minutes // minutes) * minutes
        
        # Create candle start time
        candle_start = timestamp.replace(
            hour=candle_minutes // 60,
            minute=candle_minutes % 60,
            second=0,
            microsecond=0
        )
        
        return candle_start
    
    def _create_new_candle(self, tick: Tick, timeframe: str, start_time: datetime) -> Candle:
        """
        Create a new candle from a tick.
        
        Args:
            tick: Tick data
            timeframe: Timeframe string
            start_time: Candle start time
        
        Returns:
            New Candle object
        """
        return Candle(
            timestamp=start_time,
            open=tick.last_price,
            high=tick.last_price,
            low=tick.last_price,
            close=tick.last_price,
            volume=tick.volume,
            timeframe=timeframe
        )
    
    def _update_existing_candle(self, candle: Candle, tick: Tick) -> None:
        """
        Update an existing candle with new tick data.
        
        Args:
            candle: Candle to update (modified in place)
            tick: New tick data
        """
        # Update high
        if tick.last_price > candle.high:
            candle.high = tick.last_price
        
        # Update low
        if tick.last_price < candle.low:
            candle.low = tick.last_price
        
        # Update close (always latest price)
        candle.close = tick.last_price
        
        # Accumulate volume
        candle.volume += tick.volume
    
    def get_candles(self, timeframe: str, count: int) -> List[Candle]:
        """
        Get last N completed candles for a timeframe.
        
        Args:
            timeframe: Timeframe string
            count: Number of candles to retrieve
        
        Returns:
            List of candles (most recent last)
        
        Raises:
            ValueError: If timeframe is not configured
        """
        if timeframe not in self.timeframes:
            raise ValueError(f"Timeframe {timeframe} not configured")
        
        historical = list(self.historical_candles[timeframe])
        
        # Return last N candles
        if count <= 0:
            return []
        
        return historical[-count:] if len(historical) >= count else historical
    
    def get_current_candle(self, timeframe: str) -> Optional[Candle]:
        """
        Get the current (incomplete) candle for a timeframe.
        
        Args:
            timeframe: Timeframe string
        
        Returns:
            Current candle or None if not yet initialized
        
        Raises:
            ValueError: If timeframe is not configured
        """
        if timeframe not in self.timeframes:
            raise ValueError(f"Timeframe {timeframe} not configured")
        
        return self.current_candles[timeframe]
    
    def get_historical_count(self, timeframe: str) -> int:
        """
        Get the number of historical candles available for a timeframe.
        
        Args:
            timeframe: Timeframe string
        
        Returns:
            Number of historical candles
        
        Raises:
            ValueError: If timeframe is not configured
        """
        if timeframe not in self.timeframes:
            raise ValueError(f"Timeframe {timeframe} not configured")
        
        return len(self.historical_candles[timeframe])
