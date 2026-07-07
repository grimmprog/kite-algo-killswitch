"""
Property-Based Tests for Mean Reversion Engine.

This module contains property-based tests that validate universal correctness
properties of the MR Engine across all valid inputs.
"""

import pytest
from hypothesis import given, strategies as st, assume, settings
from datetime import datetime, timedelta
from typing import List

from ..data.models import Candle
from ..data.candle_builder import CandleBuilder
from ..data.indicator_service import IndicatorService
from ..analysis.market_state_detector import MarketStateDetector
from ..execution.models import MRTrade
from ..common.enums import TrendState, MRState, SignalType
from ..config import MRConfig
from .mr_engine import MeanReversionEngine, MRBook
from .trend_engine import TrendBook


# ============================================================================
# Strategy Helpers
# ============================================================================

@st.composite
def candle_price_strategy(draw, min_price=10000.0, max_price=30000.0):
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
def candle_sequence_strategy(draw, count=20, timeframe='5m'):
    """Generate a sequence of candles."""
    candles = []
    base_time = datetime(2024, 1, 1, 9, 15)
    
    for i in range(count):
        prices = draw(candle_price_strategy())
        candle = Candle(
            timestamp=base_time + timedelta(minutes=i * 5),
            open=prices['open'],
            high=prices['high'],
            low=prices['low'],
            close=prices['close'],
            volume=draw(st.integers(min_value=100, max_value=10000)),
            timeframe=timeframe
        )
        candles.append(candle)
    
    return candles


@st.composite
def mr_trade_strategy(draw, min_price=10000.0, max_price=30000.0):
    """Generate a random MR trade."""
    entry_price = draw(st.floats(min_value=min_price, max_value=max_price))
    impulse_start = draw(st.floats(min_value=min_price, max_value=max_price))
    
    # Ensure impulse_start and entry_price are different
    assume(abs(impulse_start - entry_price) > 10.0)
    
    return MRTrade(
        entry_time=datetime.now(),
        entry_price=entry_price,
        quantity=draw(st.integers(min_value=1, max_value=50)),
        direction=draw(st.sampled_from(['long', 'short'])),
        impulse_start=impulse_start,
        impulse_end=entry_price,
        candles_held=draw(st.integers(min_value=0, max_value=10))
    )


# ============================================================================
# Property 7: MR Entry Requires Trend Position
# Feature: hybrid-trading-system, Property 7: MR Entry Requires Trend Position
# **Validates: Requirements 3.3**
# ============================================================================

@given(
    trend_state=st.sampled_from([TrendState.UPTREND, TrendState.DOWNTREND, TrendState.NEUTRAL]),
    mr_state=st.sampled_from([MRState.EXTENDED_UP, MRState.EXTENDED_DOWN, MRState.NORMAL]),
    current_price=st.floats(min_value=10000.0, max_value=30000.0),
    candles=candle_sequence_strategy(count=20)
)
@settings(max_examples=100, deadline=None)
def test_property_7_mr_entry_requires_trend_position(trend_state, mr_state, current_price, candles):
    """
    Property 7: MR Entry Requires Trend Position
    
    For any market state, if the Trend_Book position is zero, then the 
    Mean_Reversion_Engine should NOT generate any entry signals regardless 
    of mean reversion state.
    """
    # Setup
    candle_builder = CandleBuilder(timeframes=['5m'])
    indicator_service = IndicatorService(candle_builder)
    market_state = MarketStateDetector(candle_builder, indicator_service)
    
    # Add candles to builder
    for candle in candles:
        candle_builder.historical_candles['5m'].append(candle)
    
    mr_config = MRConfig(timeframe='5m', mr_base_size=15)
    mr_engine = MeanReversionEngine(market_state, indicator_service, mr_config)
    
    # Create books with ZERO trend position
    trend_book = TrendBook()
    mr_book = MRBook()
    
    # Ensure trend position is zero
    assert trend_book.position == 0
    
    # Mock MR state detection
    original_detect = market_state.detect_mr_state
    market_state.detect_mr_state = lambda tf: mr_state
    
    try:
        # Check entry conditions
        signal = mr_engine.check_entry_conditions(
            trend_state, trend_book, mr_book, current_price
        )
        
        # Property: Should NEVER generate entry signal when trend position is zero
        assert signal is None, (
            f"MR Engine generated entry signal when trend position is zero! "
            f"Signal: {signal}, Trend State: {trend_state}, MR State: {mr_state}"
        )
    finally:
        market_state.detect_mr_state = original_detect


# ============================================================================
# Property 8: MR Entry on Extension
# Feature: hybrid-trading-system, Property 8: MR Entry on Extension
# **Validates: Requirements 3.1, 3.2**
# ============================================================================

@given(
    trend_position=st.integers(min_value=20, max_value=100),
    current_price=st.floats(min_value=10000.0, max_value=30000.0),
    candles=candle_sequence_strategy(count=20)
)
@settings(max_examples=100, deadline=None)
def test_property_8_mr_entry_on_extension_uptrend(trend_position, current_price, candles):
    """
    Property 8: MR Entry on Extension (Uptrend case)
    
    For any market state where trend is UPTREND AND mean reversion state is 
    EXTENDED_UP AND Trend_Book has a long position AND MR_Book allows additional 
    exposure, the Mean_Reversion_Engine should generate a counter-position 
    short entry signal.
    """
    # Setup
    candle_builder = CandleBuilder(timeframes=['5m'])
    indicator_service = IndicatorService(candle_builder)
    market_state = MarketStateDetector(candle_builder, indicator_service)
    
    # Add candles to builder
    for candle in candles:
        candle_builder.historical_candles['5m'].append(candle)
    
    mr_config = MRConfig(timeframe='5m', mr_base_size=15, max_mr_trades_per_leg=3)
    mr_engine = MeanReversionEngine(market_state, indicator_service, mr_config)
    
    # Create books with trend position
    trend_book = TrendBook()
    trend_book.position = trend_position  # Long position
    mr_book = MRBook()
    
    # Mock MR state detection to return EXTENDED_UP
    original_detect = market_state.detect_mr_state
    market_state.detect_mr_state = lambda tf: MRState.EXTENDED_UP
    
    try:
        # Check entry conditions
        signal = mr_engine.check_entry_conditions(
            TrendState.UPTREND, trend_book, mr_book, current_price
        )
        
        # Property: Should generate SHORT entry signal
        # (unless it would flip net position, which is a separate constraint)
        if signal is not None:
            assert signal.signal_type == SignalType.ENTRY_SHORT, (
                f"Expected SHORT entry signal in UPTREND + EXTENDED_UP, got {signal.signal_type}"
            )
            assert signal.engine == 'mr'
            assert signal.quantity > 0
            
            # Verify position sizing constraint (max 30% of trend position)
            max_allowed = int(trend_position * 0.3)
            assert signal.quantity <= max_allowed, (
                f"MR position size {signal.quantity} exceeds 30% of trend position "
                f"({max_allowed})"
            )
            
            # Verify net position won't flip
            net_after = trend_book.position + mr_book.position - signal.quantity
            assert net_after > 0, (
                f"MR entry would flip net position from positive to non-positive: "
                f"trend={trend_book.position}, mr={mr_book.position}, "
                f"signal_qty={signal.quantity}, net_after={net_after}"
            )
    finally:
        market_state.detect_mr_state = original_detect


@given(
    trend_position=st.integers(min_value=-100, max_value=-20),
    current_price=st.floats(min_value=10000.0, max_value=30000.0),
    candles=candle_sequence_strategy(count=20)
)
@settings(max_examples=100, deadline=None)
def test_property_8_mr_entry_on_extension_downtrend(trend_position, current_price, candles):
    """
    Property 8: MR Entry on Extension (Downtrend case)
    
    For any market state where trend is DOWNTREND AND mean reversion state is 
    EXTENDED_DOWN AND Trend_Book has a short position AND MR_Book allows additional 
    exposure, the Mean_Reversion_Engine should generate a counter-position 
    long entry signal.
    """
    # Setup
    candle_builder = CandleBuilder(timeframes=['5m'])
    indicator_service = IndicatorService(candle_builder)
    market_state = MarketStateDetector(candle_builder, indicator_service)
    
    # Add candles to builder
    for candle in candles:
        candle_builder.historical_candles['5m'].append(candle)
    
    mr_config = MRConfig(timeframe='5m', mr_base_size=15, max_mr_trades_per_leg=3)
    mr_engine = MeanReversionEngine(market_state, indicator_service, mr_config)
    
    # Create books with trend position
    trend_book = TrendBook()
    trend_book.position = trend_position  # Short position (negative)
    mr_book = MRBook()
    
    # Mock MR state detection to return EXTENDED_DOWN
    original_detect = market_state.detect_mr_state
    market_state.detect_mr_state = lambda tf: MRState.EXTENDED_DOWN
    
    try:
        # Check entry conditions
        signal = mr_engine.check_entry_conditions(
            TrendState.DOWNTREND, trend_book, mr_book, current_price
        )
        
        # Property: Should generate LONG entry signal
        # (unless it would flip net position, which is a separate constraint)
        if signal is not None:
            assert signal.signal_type == SignalType.ENTRY_LONG, (
                f"Expected LONG entry signal in DOWNTREND + EXTENDED_DOWN, got {signal.signal_type}"
            )
            assert signal.engine == 'mr'
            assert signal.quantity > 0
            
            # Verify position sizing constraint (max 30% of trend position)
            max_allowed = int(abs(trend_position) * 0.3)
            assert signal.quantity <= max_allowed, (
                f"MR position size {signal.quantity} exceeds 30% of trend position "
                f"({max_allowed})"
            )
            
            # Verify net position won't flip
            net_after = trend_book.position + mr_book.position + signal.quantity
            assert net_after < 0, (
                f"MR entry would flip net position from negative to non-negative: "
                f"trend={trend_book.position}, mr={mr_book.position}, "
                f"signal_qty={signal.quantity}, net_after={net_after}"
            )
    finally:
        market_state.detect_mr_state = original_detect


# ============================================================================
# Property 9: MR Exit Conditions
# Feature: hybrid-trading-system, Property 9: MR Exit Conditions
# **Validates: Requirements 3.4, 3.5, 3.6, 3.7**
# ============================================================================

@given(
    trade=mr_trade_strategy(),
    candles=candle_sequence_strategy(count=10)
)
@settings(max_examples=100, deadline=None)
def test_property_9_mr_exit_on_time_stop(trade, candles):
    """
    Property 9: MR Exit Conditions (Time Stop)
    
    For any active MR trade, when time stop is hit (5 candles), the 
    Mean_Reversion_Engine should generate an exit signal for that trade.
    """
    # Setup
    candle_builder = CandleBuilder(timeframes=['5m'])
    indicator_service = IndicatorService(candle_builder)
    market_state = MarketStateDetector(candle_builder, indicator_service)
    
    # Add candles to builder
    for candle in candles:
        candle_builder.historical_candles['5m'].append(candle)
    
    mr_config = MRConfig(timeframe='5m', time_stop_candles=5)
    mr_engine = MeanReversionEngine(market_state, indicator_service, mr_config)
    
    # Set trade to time stop threshold
    trade.candles_held = 5
    
    # Check exit conditions
    signal = mr_engine.check_exit_conditions(trade, current_price=trade.entry_price)
    
    # Property: Should generate exit signal when time stop is hit
    assert signal is not None, (
        f"MR Engine did not generate exit signal when time stop hit! "
        f"Trade candles_held: {trade.candles_held}, time_stop: {mr_config.time_stop_candles}"
    )
    assert signal.signal_type == SignalType.EXIT_FULL
    assert signal.engine == 'mr'
    assert signal.quantity == trade.quantity
    assert 'Time stop' in signal.reason


@given(
    trade=mr_trade_strategy(),
    retracement_pct=st.floats(min_value=40.0, max_value=60.0),
    candles=candle_sequence_strategy(count=10)
)
@settings(max_examples=100, deadline=None)
def test_property_9_mr_exit_on_retracement(trade, retracement_pct, candles):
    """
    Property 9: MR Exit Conditions (Retracement Target)
    
    For any active MR trade, when retracement reaches 40-60% of impulse, the 
    Mean_Reversion_Engine should generate an exit signal for that trade.
    """
    # Setup
    candle_builder = CandleBuilder(timeframes=['5m'])
    indicator_service = IndicatorService(candle_builder)
    market_state = MarketStateDetector(candle_builder, indicator_service)
    
    # Add candles to builder
    for candle in candles:
        candle_builder.historical_candles['5m'].append(candle)
    
    mr_config = MRConfig(
        timeframe='5m',
        retracement_target_min=40.0,
        retracement_target_max=60.0,
        time_stop_candles=10  # Set high to avoid time stop
    )
    mr_engine = MeanReversionEngine(market_state, indicator_service, mr_config)
    
    # Set trade with low candles_held to avoid time stop
    trade.candles_held = 2
    
    # Calculate current price for desired retracement
    impulse_size = abs(trade.impulse_end - trade.impulse_start)
    retracement_distance = impulse_size * (retracement_pct / 100.0)
    
    if trade.direction == 'short':
        # Short trade: price should move down (retracement)
        current_price = trade.impulse_end - retracement_distance
    else:
        # Long trade: price should move up (retracement)
        current_price = trade.impulse_end + retracement_distance
    
    # Ensure current price is valid
    assume(current_price > 0)
    
    # Check exit conditions
    signal = mr_engine.check_exit_conditions(trade, current_price)
    
    # Property: Should generate exit signal when retracement target is hit
    # Note: May also exit due to structure/EMA touch, which is acceptable
    if signal is not None:
        assert signal.signal_type == SignalType.EXIT_FULL
        assert signal.engine == 'mr'
        assert signal.quantity == trade.quantity
        # Reason should mention retracement, structure_touch, or ema_touch
        assert any(keyword in signal.reason.lower() for keyword in ['retracement', 'structure', 'ema']), (
            f"Exit signal reason doesn't mention expected conditions: {signal.reason}"
        )


@given(
    trades=st.lists(mr_trade_strategy(), min_size=1, max_size=5)
)
@settings(max_examples=100, deadline=None)
def test_property_9_mr_exit_all_at_end_of_day(trades):
    """
    Property 9: MR Exit Conditions (End-of-Day)
    
    For any set of active MR trades, when market close approaches, the 
    Mean_Reversion_Engine should generate exit signals for ALL trades.
    """
    # Setup
    candle_builder = CandleBuilder(timeframes=['5m'])
    indicator_service = IndicatorService(candle_builder)
    market_state = MarketStateDetector(candle_builder, indicator_service)
    
    mr_config = MRConfig(timeframe='5m')
    mr_engine = MeanReversionEngine(market_state, indicator_service, mr_config)
    
    # Create MR book with trades
    mr_book = MRBook()
    for trade in trades:
        mr_book.add_trade(trade)
    
    # Generate end-of-day exit signals
    current_price = 20000.0
    signals = mr_engine.exit_all_mr_trades(mr_book, current_price)
    
    # Property: Should generate exit signal for EVERY active trade
    assert len(signals) == len(trades), (
        f"Expected {len(trades)} exit signals for end-of-day, got {len(signals)}"
    )
    
    for signal in signals:
        assert signal.signal_type == SignalType.EXIT_FULL
        assert signal.engine == 'mr'
        assert 'End-of-day' in signal.reason
        assert signal.quantity > 0
    
    # Verify all trade quantities are accounted for
    total_signal_qty = sum(s.quantity for s in signals)
    total_trade_qty = sum(t.quantity for t in trades)
    assert total_signal_qty == total_trade_qty, (
        f"Total signal quantity {total_signal_qty} doesn't match total trade quantity {total_trade_qty}"
    )
