"""
Unit tests for Mean Reversion Engine.
"""

import pytest
from datetime import datetime, timedelta

from ..data.models import Candle
from ..data.candle_builder import CandleBuilder
from ..data.indicator_service import IndicatorService
from ..analysis.market_state_detector import MarketStateDetector
from ..execution.models import MRTrade, Signal
from ..common.enums import TrendState, MRState, SignalType
from ..config import MRConfig
from .mr_engine import MeanReversionEngine, MRBook
from .trend_engine import TrendBook


@pytest.fixture
def candle_builder():
    """Create a CandleBuilder instance."""
    return CandleBuilder(timeframes=['5m', '15m'])


@pytest.fixture
def indicator_service(candle_builder):
    """Create an IndicatorService instance."""
    return IndicatorService(candle_builder)


@pytest.fixture
def market_state(candle_builder, indicator_service):
    """Create a MarketStateDetector instance."""
    return MarketStateDetector(candle_builder, indicator_service)


@pytest.fixture
def mr_config():
    """Create an MRConfig instance."""
    return MRConfig(
        timeframe='5m',
        mr_base_size=15,
        max_mr_trades_per_leg=3,
        retracement_target_min=40.0,
        retracement_target_max=60.0,
        time_stop_candles=5
    )


@pytest.fixture
def mr_engine(market_state, indicator_service, mr_config):
    """Create a MeanReversionEngine instance."""
    return MeanReversionEngine(market_state, indicator_service, mr_config)


@pytest.fixture
def trend_book():
    """Create a TrendBook instance."""
    return TrendBook()


@pytest.fixture
def mr_book():
    """Create an MRBook instance."""
    return MRBook()


def add_candles_to_builder(candle_builder, timeframe, count, base_price=20000):
    """Helper to add candles to builder."""
    base_time = datetime(2024, 1, 1, 9, 15)
    
    for i in range(count):
        candle = Candle(
            timestamp=base_time + timedelta(minutes=i * 5),
            open=base_price + i * 10,
            high=base_price + i * 10 + 20,
            low=base_price + i * 10 - 10,
            close=base_price + i * 10 + 5,
            volume=1000,
            timeframe=timeframe
        )
        candle_builder.historical_candles[timeframe].append(candle)


class TestMRBook:
    """Tests for MRBook class."""
    
    def test_add_long_trade(self, mr_book):
        """Test adding a long MR trade."""
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=20000.0,
            quantity=10,
            direction='long',
            impulse_start=19900.0,
            impulse_end=20000.0,
            candles_held=0
        )
        
        mr_book.add_trade(trade)
        
        assert len(mr_book.active_trades) == 1
        assert mr_book.position == 10
        assert mr_book.active_trades[0] == trade
    
    def test_add_short_trade(self, mr_book):
        """Test adding a short MR trade."""
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=20000.0,
            quantity=10,
            direction='short',
            impulse_start=20100.0,
            impulse_end=20000.0,
            candles_held=0
        )
        
        mr_book.add_trade(trade)
        
        assert len(mr_book.active_trades) == 1
        assert mr_book.position == -10
        assert mr_book.active_trades[0] == trade
    
    def test_close_trade(self, mr_book):
        """Test closing an MR trade."""
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=20000.0,
            quantity=10,
            direction='long',
            impulse_start=19900.0,
            impulse_end=20000.0,
            candles_held=0
        )
        
        mr_book.add_trade(trade)
        assert mr_book.position == 10
        
        mr_book.close_trade(trade, exit_price=20050.0)
        
        assert len(mr_book.active_trades) == 0
        assert mr_book.position == 0
    
    def test_close_nonexistent_trade_raises_error(self, mr_book):
        """Test that closing a nonexistent trade raises an error."""
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=20000.0,
            quantity=10,
            direction='long',
            impulse_start=19900.0,
            impulse_end=20000.0,
            candles_held=0
        )
        
        with pytest.raises(ValueError, match="Trade not found"):
            mr_book.close_trade(trade, exit_price=20050.0)


class TestMREngineEntry:
    """Tests for MR Engine entry logic."""
    
    def test_no_entry_when_trend_position_zero(self, mr_engine, trend_book, mr_book):
        """Test that MR engine doesn't generate entry when trend position is zero."""
        # Trend position is zero
        assert trend_book.position == 0
        
        # Try to generate entry signal
        signal = mr_engine.check_entry_conditions(
            TrendState.UPTREND, trend_book, mr_book, current_price=20000.0
        )
        
        assert signal is None
    
    def test_entry_short_on_extended_up_in_uptrend(self, mr_engine, trend_book, mr_book, candle_builder):
        """Test MR short entry when extended up in uptrend."""
        # Set up trend position (long)
        trend_book.position = 50
        
        # Add candles to builder
        add_candles_to_builder(candle_builder, '5m', 20, base_price=20000)
        
        # Mock MR state detection to return EXTENDED_UP
        original_detect = mr_engine.market_state.detect_mr_state
        mr_engine.market_state.detect_mr_state = lambda tf: MRState.EXTENDED_UP
        
        try:
            signal = mr_engine.check_entry_conditions(
                TrendState.UPTREND, trend_book, mr_book, current_price=20200.0
            )
            
            assert signal is not None
            assert signal.signal_type == SignalType.ENTRY_SHORT
            assert signal.engine == 'mr'
            assert signal.quantity == 15  # mr_base_size
            assert 'Extended up in uptrend' in signal.reason
        finally:
            mr_engine.market_state.detect_mr_state = original_detect
    
    def test_entry_long_on_extended_down_in_downtrend(self, mr_engine, trend_book, mr_book, candle_builder):
        """Test MR long entry when extended down in downtrend."""
        # Set up trend position (short)
        trend_book.position = -50
        
        # Add candles to builder
        add_candles_to_builder(candle_builder, '5m', 20, base_price=20000)
        
        # Mock MR state detection to return EXTENDED_DOWN
        original_detect = mr_engine.market_state.detect_mr_state
        mr_engine.market_state.detect_mr_state = lambda tf: MRState.EXTENDED_DOWN
        
        try:
            signal = mr_engine.check_entry_conditions(
                TrendState.DOWNTREND, trend_book, mr_book, current_price=19800.0
            )
            
            assert signal is not None
            assert signal.signal_type == SignalType.ENTRY_LONG
            assert signal.engine == 'mr'
            assert signal.quantity == 15  # mr_base_size
            assert 'Extended down in downtrend' in signal.reason
        finally:
            mr_engine.market_state.detect_mr_state = original_detect
    
    def test_mr_size_limited_to_30_percent_of_trend(self, mr_engine, trend_book, mr_book, candle_builder):
        """Test that MR position size is limited to 30% of trend position."""
        # Set up small trend position
        trend_book.position = 20
        
        # Add candles to builder
        add_candles_to_builder(candle_builder, '5m', 20, base_price=20000)
        
        # Mock MR state detection
        original_detect = mr_engine.market_state.detect_mr_state
        mr_engine.market_state.detect_mr_state = lambda tf: MRState.EXTENDED_UP
        
        try:
            signal = mr_engine.check_entry_conditions(
                TrendState.UPTREND, trend_book, mr_book, current_price=20200.0
            )
            
            assert signal is not None
            # 30% of 20 = 6, which is less than mr_base_size (15)
            assert signal.quantity == 6
        finally:
            mr_engine.market_state.detect_mr_state = original_detect
    
    def test_no_entry_if_would_flip_net_position(self, mr_engine, trend_book, mr_book, candle_builder):
        """Test that MR entry is rejected if it would flip net position."""
        # Set up small trend position (long) and existing MR position
        trend_book.position = 10
        
        # Add existing MR short position that brings net close to zero
        existing_trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=20150.0,
            quantity=8,
            direction='short',
            impulse_start=20050.0,
            impulse_end=20150.0,
            candles_held=1
        )
        mr_book.add_trade(existing_trade)
        # Net position is now 10 - 8 = 2
        
        # Add candles to builder
        add_candles_to_builder(candle_builder, '5m', 20, base_price=20000)
        
        # Mock MR state detection
        original_detect = mr_engine.market_state.detect_mr_state
        mr_engine.market_state.detect_mr_state = lambda tf: MRState.EXTENDED_UP
        
        try:
            # MR short of 3 (30% of 10) would flip position from +2 to -1
            signal = mr_engine.check_entry_conditions(
                TrendState.UPTREND, trend_book, mr_book, current_price=20200.0
            )
            
            # Should be rejected
            assert signal is None
        finally:
            mr_engine.market_state.detect_mr_state = original_detect


class TestMREngineExit:
    """Tests for MR Engine exit logic."""
    
    def test_exit_on_retracement_target(self, mr_engine, candle_builder):
        """Test exit when retracement target is hit."""
        # Create MR trade
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=20100.0,
            quantity=10,
            direction='short',
            impulse_start=20000.0,
            impulse_end=20100.0,  # 100 point impulse
            candles_held=2
        )
        
        # Add candles to builder
        add_candles_to_builder(candle_builder, '5m', 20, base_price=20000)
        
        # Current price at 50% retracement (20050)
        signal = mr_engine.check_exit_conditions(trade, current_price=20050.0)
        
        assert signal is not None
        assert signal.signal_type == SignalType.EXIT_FULL
        assert signal.engine == 'mr'
        assert signal.quantity == 10
        assert 'retracement=' in signal.reason
    
    def test_exit_on_time_stop(self, mr_engine, candle_builder):
        """Test exit when time stop is hit."""
        # Create MR trade that has been held for 5 candles
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=20100.0,
            quantity=10,
            direction='short',
            impulse_start=20000.0,
            impulse_end=20100.0,
            candles_held=5  # Time stop threshold
        )
        
        # Add candles to builder
        add_candles_to_builder(candle_builder, '5m', 20, base_price=20000)
        
        # Current price hasn't retraced much
        signal = mr_engine.check_exit_conditions(trade, current_price=20090.0)
        
        assert signal is not None
        assert signal.signal_type == SignalType.EXIT_FULL
        assert 'Time stop hit' in signal.reason
    
    def test_exit_on_momentum_loss(self, mr_engine, candle_builder):
        """Test exit when momentum loss candle appears."""
        # Create MR short trade
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=20100.0,
            quantity=10,
            direction='short',
            impulse_start=20000.0,
            impulse_end=20100.0,
            candles_held=2
        )
        
        # Add candles with a large bullish candle at the end (momentum loss for short)
        # Use smaller body sizes to avoid hitting retracement target
        base_time = datetime(2024, 1, 1, 9, 15)
        for i in range(4):
            candle = Candle(
                timestamp=base_time + timedelta(minutes=i * 5),
                open=20100.0,
                high=20105.0,
                low=20095.0,
                close=20102.0,  # Small body
                volume=1000,
                timeframe='5m'
            )
            candle_builder.historical_candles['5m'].append(candle)
        
        # Add large bullish candle (momentum loss) but not enough to hit retracement
        large_candle = Candle(
            timestamp=base_time + timedelta(minutes=4 * 5),
            open=20102.0,
            high=20125.0,
            low=20100.0,
            close=20120.0,  # Large body (18 points vs avg ~2 points)
            volume=1000,
            timeframe='5m'
        )
        candle_builder.historical_candles['5m'].append(large_candle)
        
        # Current price at 20120 gives retracement of 20% (not in 40-60% range)
        signal = mr_engine.check_exit_conditions(trade, current_price=20120.0)
        
        assert signal is not None
        assert signal.signal_type == SignalType.EXIT_FULL
        assert 'Momentum loss' in signal.reason
    
    def test_no_exit_when_conditions_not_met(self, mr_engine, candle_builder):
        """Test no exit when no conditions are met."""
        # Create MR trade
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=20100.0,
            quantity=10,
            direction='short',
            impulse_start=20000.0,
            impulse_end=20100.0,
            candles_held=2
        )
        
        # Add candles to builder
        add_candles_to_builder(candle_builder, '5m', 20, base_price=20000)
        
        # Current price hasn't retraced enough (only 10% retracement)
        signal = mr_engine.check_exit_conditions(trade, current_price=20090.0)
        
        assert signal is None


class TestMREngineEndOfDay:
    """Tests for end-of-day MR exit logic."""
    
    def test_exit_all_mr_trades(self, mr_engine, mr_book):
        """Test that all MR trades are exited at end of day."""
        # Add multiple MR trades
        trade1 = MRTrade(
            entry_time=datetime.now(),
            entry_price=20100.0,
            quantity=10,
            direction='short',
            impulse_start=20000.0,
            impulse_end=20100.0,
            candles_held=2
        )
        trade2 = MRTrade(
            entry_time=datetime.now(),
            entry_price=20150.0,
            quantity=5,
            direction='short',
            impulse_start=20050.0,
            impulse_end=20150.0,
            candles_held=1
        )
        
        mr_book.add_trade(trade1)
        mr_book.add_trade(trade2)
        
        # Generate end-of-day exit signals
        signals = mr_engine.exit_all_mr_trades(mr_book, current_price=20120.0)
        
        assert len(signals) == 2
        assert all(s.signal_type == SignalType.EXIT_FULL for s in signals)
        assert all(s.engine == 'mr' for s in signals)
        assert all('End-of-day' in s.reason for s in signals)
        assert signals[0].quantity == 10
        assert signals[1].quantity == 5


class TestMREngineEvaluate:
    """Tests for MR Engine evaluate method."""
    
    def test_evaluate_generates_exit_before_entry(self, mr_engine, trend_book, mr_book, candle_builder):
        """Test that evaluate checks exits before entries."""
        # Set up trend position
        trend_book.position = 50
        
        # Add an MR trade that should exit
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=20100.0,
            quantity=10,
            direction='short',
            impulse_start=20000.0,
            impulse_end=20100.0,
            candles_held=5  # Time stop
        )
        mr_book.add_trade(trade)
        
        # Add candles to builder
        add_candles_to_builder(candle_builder, '5m', 20, base_price=20000)
        
        # Evaluate
        signals = mr_engine.evaluate(
            TrendState.UPTREND, trend_book, mr_book, current_price=20090.0
        )
        
        # Should generate exit signal
        assert len(signals) >= 1
        assert signals[0].signal_type == SignalType.EXIT_FULL
    
    def test_evaluate_respects_max_trades_limit(self, mr_engine, trend_book, mr_book, candle_builder):
        """Test that evaluate respects max MR trades per leg limit."""
        # Set up trend position
        trend_book.position = 50
        
        # Add max number of MR trades
        for i in range(3):  # max_mr_trades_per_leg = 3
            trade = MRTrade(
                entry_time=datetime.now(),
                entry_price=20100.0 + i * 10,
                quantity=10,
                direction='short',
                impulse_start=20000.0,
                impulse_end=20100.0 + i * 10,
                candles_held=1
            )
            mr_book.add_trade(trade)
        
        # Add candles to builder
        add_candles_to_builder(candle_builder, '5m', 20, base_price=20000)
        
        # Mock MR state detection
        original_detect = mr_engine.market_state.detect_mr_state
        mr_engine.market_state.detect_mr_state = lambda tf: MRState.EXTENDED_UP
        
        try:
            # Evaluate - should not generate new entry
            signals = mr_engine.evaluate(
                TrendState.UPTREND, trend_book, mr_book, current_price=20200.0
            )
            
            # Should not have any entry signals (only possible exits)
            entry_signals = [s for s in signals if s.signal_type in (SignalType.ENTRY_LONG, SignalType.ENTRY_SHORT)]
            assert len(entry_signals) == 0
        finally:
            mr_engine.market_state.detect_mr_state = original_detect
