"""
Property-Based Tests for Trend Engine Exit Logic.

Property 5: Trend Exit on Structure Break
**Validates: Requirements 2.5, 2.6**

For any Trend_Book position, when a structure break occurs on the 15-minute timeframe 
OR an opposite trend is confirmed (2 consecutive closes beyond previous structure AND 
full HH/LL flip), the Trend_Engine should generate a full exit signal.
"""

import pytest
from hypothesis import given, strategies as st, assume, settings
from datetime import datetime, timedelta
from typing import List

from ..data.models import Candle
from ..data.candle_builder import CandleBuilder
from ..data.indicator_service import IndicatorService
from ..analysis.market_state_detector import MarketStateDetector
from ..common.enums import TrendState, SignalType
from ..config import TrendConfig
from .trend_engine import TrendEngine, TrendBook


# Strategy for generating candle prices
@st.composite
def candle_price_strategy(draw, min_price=50.0, max_price=200.0):
    """Generate realistic OHLC prices for a candle."""
    open_price = draw(st.floats(min_value=min_price, max_value=max_price))
    close_price = draw(st.floats(min_value=min_price, max_value=max_price))
    
    # High must be >= max(open, close)
    high_min = max(open_price, close_price)
    high_price = draw(st.floats(min_value=high_min, max_value=max_price))
    
    # Low must be <= min(open, close)
    low_max = min(open_price, close_price)
    low_price = draw(st.floats(min_value=min_price, max_value=low_max))
    
    return {
        'open': open_price,
        'high': high_price,
        'low': low_price,
        'close': close_price
    }


@st.composite
def uptrend_candles_with_structure_break(draw):
    """
    Generate an uptrend pattern followed by a structure break.
    
    Uptrend: Higher highs and higher lows
    Structure break: Price breaks below previous higher low
    """
    base_time = datetime.now()
    candles = []
    
    # Generate uptrend: 10-20 candles with higher highs and higher lows
    num_uptrend_candles = draw(st.integers(min_value=10, max_value=20))
    
    current_low = 100.0
    current_high = 105.0
    
    for i in range(num_uptrend_candles):
        # Create higher low and higher high
        low = current_low + draw(st.floats(min_value=0.5, max_value=2.0))
        high = current_high + draw(st.floats(min_value=0.5, max_value=2.0))
        
        open_price = draw(st.floats(min_value=low, max_value=high))
        close_price = draw(st.floats(min_value=low, max_value=high))
        
        candle = Candle(
            timestamp=base_time + timedelta(minutes=15 * i),
            open=open_price,
            high=high,
            low=low,
            close=close_price,
            volume=1000,
            timeframe='15m'
        )
        candles.append(candle)
        
        current_low = low
        current_high = high
    
    # Record the last higher low (structure level)
    structure_level = current_low
    
    # Generate structure break: candle that breaks below the last higher low
    break_low = structure_level - draw(st.floats(min_value=1.0, max_value=5.0))
    break_high = structure_level + draw(st.floats(min_value=0.5, max_value=2.0))
    break_open = draw(st.floats(min_value=break_low, max_value=break_high))
    break_close = draw(st.floats(min_value=break_low, max_value=structure_level - 0.5))
    
    break_candle = Candle(
        timestamp=base_time + timedelta(minutes=15 * num_uptrend_candles),
        open=break_open,
        high=break_high,
        low=break_low,
        close=break_close,
        volume=1000,
        timeframe='15m'
    )
    candles.append(break_candle)
    
    return candles, structure_level


@st.composite
def downtrend_candles_with_structure_break(draw):
    """
    Generate a downtrend pattern followed by a structure break.
    
    Downtrend: Lower highs and lower lows
    Structure break: Price breaks above previous lower high
    """
    base_time = datetime.now()
    candles = []
    
    # Generate downtrend: 10-20 candles with lower highs and lower lows
    num_downtrend_candles = draw(st.integers(min_value=10, max_value=20))
    
    current_low = 100.0
    current_high = 105.0
    
    for i in range(num_downtrend_candles):
        # Create lower low and lower high
        low = current_low - draw(st.floats(min_value=0.5, max_value=2.0))
        high = current_high - draw(st.floats(min_value=0.5, max_value=2.0))
        
        open_price = draw(st.floats(min_value=low, max_value=high))
        close_price = draw(st.floats(min_value=low, max_value=high))
        
        candle = Candle(
            timestamp=base_time + timedelta(minutes=15 * i),
            open=open_price,
            high=high,
            low=low,
            close=close_price,
            volume=1000,
            timeframe='15m'
        )
        candles.append(candle)
        
        current_low = low
        current_high = high
    
    # Record the last lower high (structure level)
    structure_level = current_high
    
    # Generate structure break: candle that breaks above the last lower high
    break_low = structure_level - draw(st.floats(min_value=0.5, max_value=2.0))
    break_high = structure_level + draw(st.floats(min_value=1.0, max_value=5.0))
    break_open = draw(st.floats(min_value=break_low, max_value=break_high))
    break_close = draw(st.floats(min_value=structure_level + 0.5, max_value=break_high))
    
    break_candle = Candle(
        timestamp=base_time + timedelta(minutes=15 * num_downtrend_candles),
        open=break_open,
        high=break_high,
        low=break_low,
        close=break_close,
        volume=1000,
        timeframe='15m'
    )
    candles.append(break_candle)
    
    return candles, structure_level


@st.composite
def uptrend_with_opposite_trend_confirmation(draw):
    """
    Generate an uptrend followed by opposite trend confirmation.
    
    Opposite trend confirmation: 2 consecutive closes beyond previous structure
    AND full HH/LL flip (downtrend pattern)
    """
    base_time = datetime.now()
    candles = []
    
    # Generate uptrend: 10-15 candles
    num_uptrend_candles = draw(st.integers(min_value=10, max_value=15))
    
    current_low = 100.0
    current_high = 105.0
    
    for i in range(num_uptrend_candles):
        low = current_low + draw(st.floats(min_value=0.5, max_value=2.0))
        high = current_high + draw(st.floats(min_value=0.5, max_value=2.0))
        
        open_price = draw(st.floats(min_value=low, max_value=high))
        close_price = draw(st.floats(min_value=low, max_value=high))
        
        candle = Candle(
            timestamp=base_time + timedelta(minutes=15 * i),
            open=open_price,
            high=high,
            low=low,
            close=close_price,
            volume=1000,
            timeframe='15m'
        )
        candles.append(candle)
        
        current_low = low
        current_high = high
    
    # Record structure level (last higher low)
    structure_level = current_low
    
    # Generate 2 consecutive candles with closes below structure (opposite trend)
    for j in range(2):
        # Create lower high and lower low pattern
        low = current_low - draw(st.floats(min_value=1.0, max_value=3.0))
        high = current_high - draw(st.floats(min_value=1.0, max_value=3.0))
        
        open_price = draw(st.floats(min_value=low, max_value=high))
        # Close must be below structure level
        close_price = draw(st.floats(min_value=low, max_value=min(high, structure_level - 0.5)))
        
        candle = Candle(
            timestamp=base_time + timedelta(minutes=15 * (num_uptrend_candles + j)),
            open=open_price,
            high=high,
            low=low,
            close=close_price,
            volume=1000,
            timeframe='15m'
        )
        candles.append(candle)
        
        current_low = low
        current_high = high
    
    return candles, structure_level


@st.composite
def downtrend_with_opposite_trend_confirmation(draw):
    """
    Generate a downtrend followed by opposite trend confirmation.
    
    Opposite trend confirmation: 2 consecutive closes beyond previous structure
    AND full HH/LL flip (uptrend pattern)
    """
    base_time = datetime.now()
    candles = []
    
    # Generate downtrend: 10-15 candles
    num_downtrend_candles = draw(st.integers(min_value=10, max_value=15))
    
    current_low = 100.0
    current_high = 105.0
    
    for i in range(num_downtrend_candles):
        low = current_low - draw(st.floats(min_value=0.5, max_value=2.0))
        high = current_high - draw(st.floats(min_value=0.5, max_value=2.0))
        
        open_price = draw(st.floats(min_value=low, max_value=high))
        close_price = draw(st.floats(min_value=low, max_value=high))
        
        candle = Candle(
            timestamp=base_time + timedelta(minutes=15 * i),
            open=open_price,
            high=high,
            low=low,
            close=close_price,
            volume=1000,
            timeframe='15m'
        )
        candles.append(candle)
        
        current_low = low
        current_high = high
    
    # Record structure level (last lower high)
    structure_level = current_high
    
    # Generate 2 consecutive candles with closes above structure (opposite trend)
    for j in range(2):
        # Create higher high and higher low pattern
        low = current_low + draw(st.floats(min_value=1.0, max_value=3.0))
        high = current_high + draw(st.floats(min_value=1.0, max_value=3.0))
        
        open_price = draw(st.floats(min_value=low, max_value=high))
        # Close must be above structure level
        close_price = draw(st.floats(min_value=max(low, structure_level + 0.5), max_value=high))
        
        candle = Candle(
            timestamp=base_time + timedelta(minutes=15 * (num_downtrend_candles + j)),
            open=open_price,
            high=high,
            low=low,
            close=close_price,
            volume=1000,
            timeframe='15m'
        )
        candles.append(candle)
        
        current_low = low
        current_high = high
    
    return candles, structure_level


class TestProperty5_TrendExitOnStructureBreak:
    """
    Property 5: Trend Exit on Structure Break
    
    For any Trend_Book position, when a structure break occurs on the 15-minute 
    timeframe OR an opposite trend is confirmed, the Trend_Engine should generate 
    a full exit signal.
    """
    
    @given(uptrend_candles_with_structure_break())
    @settings(max_examples=100, deadline=None)
    def test_structure_break_generates_full_exit_for_long_position(self, candle_data):
        """
        Property: When structure break occurs in uptrend, full exit signal is generated.
        
        Given: A long position in an uptrend
        When: Structure break occurs (price breaks below previous higher low)
        Then: Trend_Engine generates a full exit signal
        """
        candles, structure_level = candle_data
        
        # Ensure we have enough candles
        assume(len(candles) >= 15)
        
        # Set up components
        timeframes = ['15m']
        candle_builder = CandleBuilder(timeframes)
        indicator_service = IndicatorService(candle_builder)
        market_state = MarketStateDetector(candle_builder, indicator_service)
        config = TrendConfig(timeframe='15m', base_position_size=1)
        engine = TrendEngine(market_state, indicator_service, config)
        
        # Load candles into builder
        candle_builder.historical_candles['15m'] = candles
        
        # Create trend book with long position
        trend_book = TrendBook()
        trend_book.position = 10  # Long position
        trend_book.avg_entry_price = 100.0
        
        # Get current price (last candle close)
        current_price = candles[-1].close
        
        # Evaluate exit conditions
        signal = engine.check_exit_conditions(TrendState.UPTREND, trend_book, current_price)
        
        # Property assertion: Full exit signal should be generated
        assert signal is not None, "Expected full exit signal on structure break"
        assert signal.signal_type == SignalType.EXIT_FULL, \
            f"Expected EXIT_FULL, got {signal.signal_type}"
        assert signal.quantity == abs(trend_book.position), \
            f"Expected full position exit ({abs(trend_book.position)}), got {signal.quantity}"
        assert 'structure break' in signal.reason.lower() or 'opposite trend' in signal.reason.lower(), \
            f"Expected structure break or opposite trend in reason, got: {signal.reason}"
    
    @given(downtrend_candles_with_structure_break())
    @settings(max_examples=100, deadline=None)
    def test_structure_break_generates_full_exit_for_short_position(self, candle_data):
        """
        Property: When structure break occurs in downtrend, full exit signal is generated.
        
        Given: A short position in a downtrend
        When: Structure break occurs (price breaks above previous lower high)
        Then: Trend_Engine generates a full exit signal
        """
        candles, structure_level = candle_data
        
        # Ensure we have enough candles
        assume(len(candles) >= 15)
        
        # Set up components
        timeframes = ['15m']
        candle_builder = CandleBuilder(timeframes)
        indicator_service = IndicatorService(candle_builder)
        market_state = MarketStateDetector(candle_builder, indicator_service)
        config = TrendConfig(timeframe='15m', base_position_size=1)
        engine = TrendEngine(market_state, indicator_service, config)
        
        # Load candles into builder
        candle_builder.historical_candles['15m'] = candles
        
        # Create trend book with short position
        trend_book = TrendBook()
        trend_book.position = -10  # Short position
        trend_book.avg_entry_price = 100.0
        
        # Get current price (last candle close)
        current_price = candles[-1].close
        
        # Evaluate exit conditions
        signal = engine.check_exit_conditions(TrendState.DOWNTREND, trend_book, current_price)
        
        # Property assertion: Full exit signal should be generated
        assert signal is not None, "Expected full exit signal on structure break"
        assert signal.signal_type == SignalType.EXIT_FULL, \
            f"Expected EXIT_FULL, got {signal.signal_type}"
        assert signal.quantity == abs(trend_book.position), \
            f"Expected full position exit ({abs(trend_book.position)}), got {signal.quantity}"
        assert 'structure break' in signal.reason.lower() or 'opposite trend' in signal.reason.lower(), \
            f"Expected structure break or opposite trend in reason, got: {signal.reason}"
    
    @given(uptrend_with_opposite_trend_confirmation())
    @settings(max_examples=100, deadline=None)
    def test_opposite_trend_confirmation_generates_full_exit_for_long(self, candle_data):
        """
        Property: When opposite trend is confirmed, full exit signal is generated.
        
        Given: A long position in an uptrend
        When: Opposite trend confirmed (2 consecutive closes below structure + downtrend pattern)
        Then: Trend_Engine generates a full exit signal
        """
        candles, structure_level = candle_data
        
        # Ensure we have enough candles
        assume(len(candles) >= 15)
        
        # Set up components
        timeframes = ['15m']
        candle_builder = CandleBuilder(timeframes)
        indicator_service = IndicatorService(candle_builder)
        market_state = MarketStateDetector(candle_builder, indicator_service)
        config = TrendConfig(timeframe='15m', base_position_size=1)
        engine = TrendEngine(market_state, indicator_service, config)
        
        # Load candles into builder
        candle_builder.historical_candles['15m'] = candles
        
        # Create trend book with long position
        trend_book = TrendBook()
        trend_book.position = 10  # Long position
        trend_book.avg_entry_price = 100.0
        
        # Get current price (last candle close)
        current_price = candles[-1].close
        
        # Detect trend state (should be DOWNTREND after opposite trend confirmation)
        trend_state = market_state.detect_trend_state('15m')
        
        # Evaluate exit conditions
        signal = engine.check_exit_conditions(trend_state, trend_book, current_price)
        
        # Property assertion: Full exit signal should be generated
        # Note: Signal might be generated due to structure break OR opposite trend confirmation
        assert signal is not None, "Expected full exit signal on opposite trend confirmation"
        assert signal.signal_type == SignalType.EXIT_FULL, \
            f"Expected EXIT_FULL, got {signal.signal_type}"
        assert signal.quantity == abs(trend_book.position), \
            f"Expected full position exit ({abs(trend_book.position)}), got {signal.quantity}"
    
    @given(downtrend_with_opposite_trend_confirmation())
    @settings(max_examples=100, deadline=None)
    def test_opposite_trend_confirmation_generates_full_exit_for_short(self, candle_data):
        """
        Property: When opposite trend is confirmed, full exit signal is generated.
        
        Given: A short position in a downtrend
        When: Opposite trend confirmed (2 consecutive closes above structure + uptrend pattern)
        Then: Trend_Engine generates a full exit signal
        """
        candles, structure_level = candle_data
        
        # Ensure we have enough candles
        assume(len(candles) >= 15)
        
        # Set up components
        timeframes = ['15m']
        candle_builder = CandleBuilder(timeframes)
        indicator_service = IndicatorService(candle_builder)
        market_state = MarketStateDetector(candle_builder, indicator_service)
        config = TrendConfig(timeframe='15m', base_position_size=1)
        engine = TrendEngine(market_state, indicator_service, config)
        
        # Load candles into builder
        candle_builder.historical_candles['15m'] = candles
        
        # Create trend book with short position
        trend_book = TrendBook()
        trend_book.position = -10  # Short position
        trend_book.avg_entry_price = 100.0
        
        # Get current price (last candle close)
        current_price = candles[-1].close
        
        # Detect trend state (should be UPTREND after opposite trend confirmation)
        trend_state = market_state.detect_trend_state('15m')
        
        # Evaluate exit conditions
        signal = engine.check_exit_conditions(trend_state, trend_book, current_price)
        
        # Property assertion: Full exit signal should be generated
        # Note: Signal might be generated due to structure break OR opposite trend confirmation
        assert signal is not None, "Expected full exit signal on opposite trend confirmation"
        assert signal.signal_type == SignalType.EXIT_FULL, \
            f"Expected EXIT_FULL, got {signal.signal_type}"
        assert signal.quantity == abs(trend_book.position), \
            f"Expected full position exit ({abs(trend_book.position)}), got {signal.quantity}"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
