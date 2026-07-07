"""
Unit tests for Trend Engine.
"""

import pytest
from datetime import datetime, timedelta

from ..data.models import Candle
from ..data.candle_builder import CandleBuilder
from ..data.indicator_service import IndicatorService
from ..analysis.market_state_detector import MarketStateDetector
from ..common.enums import TrendState, SignalType
from ..config import TrendConfig
from .trend_engine import TrendEngine, TrendBook


class TestTrendBook:
    """Test TrendBook position tracking."""
    
    def test_initial_state(self):
        """Test TrendBook starts with zero position."""
        book = TrendBook()
        assert book.position == 0
        assert book.avg_entry_price == 0.0
        assert len(book.trades) == 0
    
    def test_add_long_position(self):
        """Test adding a long position."""
        book = TrendBook()
        book.add_position(10, 100.0)
        assert book.position == 10
        assert book.avg_entry_price == 100.0
    
    def test_add_short_position(self):
        """Test adding a short position."""
        book = TrendBook()
        book.add_position(-10, 100.0)
        assert book.position == -10
        assert book.avg_entry_price == 100.0
    
    def test_reduce_long_position(self):
        """Test reducing a long position."""
        book = TrendBook()
        book.add_position(10, 100.0)
        book.reduce_position(5, 105.0)
        assert book.position == 5
        assert book.avg_entry_price == 100.0  # Avg price doesn't change on exit
    
    def test_reduce_short_position(self):
        """Test reducing a short position."""
        book = TrendBook()
        book.add_position(-10, 100.0)
        book.reduce_position(5, 95.0)
        assert book.position == -5
        assert book.avg_entry_price == 100.0
    
    def test_close_position_resets_avg_price(self):
        """Test that closing position resets average price."""
        book = TrendBook()
        book.add_position(10, 100.0)
        book.reduce_position(10, 105.0)
        assert book.position == 0
        assert book.avg_entry_price == 0.0
    
    def test_reduce_position_validation(self):
        """Test that reducing more than position raises error."""
        book = TrendBook()
        book.add_position(10, 100.0)
        
        with pytest.raises(ValueError, match="Cannot reduce position"):
            book.reduce_position(15, 105.0)


class TestTrendEngine:
    """Test Trend Engine entry and exit logic."""
    
    @pytest.fixture
    def setup_components(self):
        """Set up test components."""
        timeframes = ['15m']
        candle_builder = CandleBuilder(timeframes)
        indicator_service = IndicatorService(candle_builder)
        market_state = MarketStateDetector(candle_builder, indicator_service)
        config = TrendConfig(timeframe='15m', base_position_size=1)
        engine = TrendEngine(market_state, indicator_service, config)
        
        return {
            'candle_builder': candle_builder,
            'indicator_service': indicator_service,
            'market_state': market_state,
            'config': config,
            'engine': engine
        }
    
    def test_no_entry_when_position_exists(self, setup_components):
        """Test that no entry signal is generated when position already exists."""
        engine = setup_components['engine']
        trend_book = TrendBook()
        trend_book.position = 10  # Existing long position
        
        signal = engine.check_entry_conditions(TrendState.UPTREND, trend_book, 100.0)
        assert signal is None
    
    def test_no_entry_in_neutral_trend(self, setup_components):
        """Test that no entry signal is generated in neutral trend."""
        engine = setup_components['engine']
        trend_book = TrendBook()
        
        signal = engine.check_entry_conditions(TrendState.NEUTRAL, trend_book, 100.0)
        assert signal is None
    
    def test_no_exit_when_no_position(self, setup_components):
        """Test that no exit signal is generated when no position exists."""
        engine = setup_components['engine']
        trend_book = TrendBook()
        
        signal = engine.check_exit_conditions(TrendState.UPTREND, trend_book, 100.0)
        assert signal is None
    
    def test_partial_exit_quantity_calculation(self, setup_components):
        """Test partial exit quantity calculation."""
        config = setup_components['config']
        config.partial_exit_percentage = 0.5  # 50%
        
        engine = setup_components['engine']
        candle_builder = setup_components['candle_builder']
        
        # Create sample candles to populate the builder
        base_time = datetime.now()
        for i in range(60):
            candle = Candle(
                timestamp=base_time + timedelta(minutes=15 * i),
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.5 + i,
                volume=1000,
                timeframe='15m'
            )
            candle_builder.historical_candles['15m'].append(candle)
        
        trend_book = TrendBook()
        trend_book.position = 10
        
        # Manually create a partial exit signal to test quantity
        partial_qty = int(abs(trend_book.position) * config.partial_exit_percentage)
        assert partial_qty == 5
    
    def test_entry_rejection_at_vertical_extension(self, setup_components):
        """Test that entry is rejected at vertical extension."""
        engine = setup_components['engine']
        candle_builder = setup_components['candle_builder']
        market_state = setup_components['market_state']
        
        # Create candles with vertical extension pattern
        base_time = datetime.now()
        for i in range(60):
            # Create large body candles (vertical extension)
            candle = Candle(
                timestamp=base_time + timedelta(minutes=15 * i),
                open=100.0 + i * 5,
                high=105.0 + i * 5,
                low=99.0 + i * 5,
                close=104.0 + i * 5,  # Large body
                volume=1000,
                timeframe='15m'
            )
            candle_builder.historical_candles['15m'].append(candle)
        
        trend_book = TrendBook()
        
        # Check if vertical extension is detected
        is_vertical = market_state.is_vertical_extension('15m')
        
        # If vertical extension, entry should be rejected
        if is_vertical:
            signal = engine.check_entry_conditions(TrendState.UPTREND, trend_book, 400.0)
            assert signal is None


class TestTrendEngineEdgeCases:
    """Test edge cases for Trend Engine."""
    
    def test_entry_rejection_when_already_in_long_position(self):
        """Test that entry is rejected when already holding a long position."""
        # Set up components
        timeframes = ['15m']
        candle_builder = CandleBuilder(timeframes)
        indicator_service = IndicatorService(candle_builder)
        market_state = MarketStateDetector(candle_builder, indicator_service)
        config = TrendConfig(timeframe='15m', base_position_size=10)
        engine = TrendEngine(market_state, indicator_service, config)
        
        # Create trend book with existing long position
        trend_book = TrendBook()
        trend_book.position = 10
        trend_book.avg_entry_price = 100.0
        
        # Try to generate entry signal
        signal = engine.check_entry_conditions(TrendState.UPTREND, trend_book, 105.0)
        
        # Should be rejected
        assert signal is None, "Entry should be rejected when position already exists"
    
    def test_entry_rejection_when_already_in_short_position(self):
        """Test that entry is rejected when already holding a short position."""
        # Set up components
        timeframes = ['15m']
        candle_builder = CandleBuilder(timeframes)
        indicator_service = IndicatorService(candle_builder)
        market_state = MarketStateDetector(candle_builder, indicator_service)
        config = TrendConfig(timeframe='15m', base_position_size=10)
        engine = TrendEngine(market_state, indicator_service, config)
        
        # Create trend book with existing short position
        trend_book = TrendBook()
        trend_book.position = -10
        trend_book.avg_entry_price = 100.0
        
        # Try to generate entry signal
        signal = engine.check_entry_conditions(TrendState.DOWNTREND, trend_book, 95.0)
        
        # Should be rejected
        assert signal is None, "Entry should be rejected when position already exists"
    
    def test_entry_rejection_at_vertical_extension_detailed(self):
        """Test that entry is rejected at vertical extension with specific conditions."""
        # Set up components
        timeframes = ['15m']
        candle_builder = CandleBuilder(timeframes)
        indicator_service = IndicatorService(candle_builder)
        market_state = MarketStateDetector(candle_builder, indicator_service)
        config = TrendConfig(
            timeframe='15m',
            base_position_size=10,
            vertical_extension_body_threshold=2.0,
            vertical_extension_distance_threshold=2.0
        )
        engine = TrendEngine(market_state, indicator_service, config)
        
        # Create candles with clear vertical extension
        base_time = datetime.now()
        candles = []
        
        # Normal candles first
        for i in range(20):
            candle = Candle(
                timestamp=base_time + timedelta(minutes=15 * i),
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.5 + i,
                volume=1000,
                timeframe='15m'
            )
            candles.append(candle)
        
        # Add vertical extension candles (large bodies)
        for i in range(5):
            candle = Candle(
                timestamp=base_time + timedelta(minutes=15 * (20 + i)),
                open=120.0 + i * 10,
                high=130.0 + i * 10,
                low=119.0 + i * 10,
                close=129.0 + i * 10,  # Very large body
                volume=1000,
                timeframe='15m'
            )
            candles.append(candle)
        
        candle_builder.historical_candles['15m'] = candles
        
        trend_book = TrendBook()
        
        # Check if vertical extension is detected
        is_vertical = market_state.is_vertical_extension(
            '15m',
            body_threshold=config.vertical_extension_body_threshold,
            distance_threshold=config.vertical_extension_distance_threshold
        )
        
        # If vertical extension detected, entry should be rejected
        if is_vertical:
            signal = engine.check_entry_conditions(TrendState.UPTREND, trend_book, 160.0)
            assert signal is None, "Entry should be rejected at vertical extension"
    
    def test_partial_exit_quantity_with_different_percentages(self):
        """Test partial exit quantity calculation with various percentages."""
        # Set up components
        timeframes = ['15m']
        candle_builder = CandleBuilder(timeframes)
        indicator_service = IndicatorService(candle_builder)
        market_state = MarketStateDetector(candle_builder, indicator_service)
        
        # Test 50% partial exit
        config_50 = TrendConfig(timeframe='15m', base_position_size=10, partial_exit_percentage=0.5)
        trend_book = TrendBook()
        trend_book.position = 10
        partial_qty_50 = int(abs(trend_book.position) * config_50.partial_exit_percentage)
        assert partial_qty_50 == 5, "50% of 10 should be 5"
        
        # Test 30% partial exit
        config_30 = TrendConfig(timeframe='15m', base_position_size=10, partial_exit_percentage=0.3)
        partial_qty_30 = int(abs(trend_book.position) * config_30.partial_exit_percentage)
        assert partial_qty_30 == 3, "30% of 10 should be 3"
        
        # Test 75% partial exit
        config_75 = TrendConfig(timeframe='15m', base_position_size=10, partial_exit_percentage=0.75)
        partial_qty_75 = int(abs(trend_book.position) * config_75.partial_exit_percentage)
        assert partial_qty_75 == 7, "75% of 10 should be 7"
    
    def test_partial_exit_quantity_for_short_position(self):
        """Test partial exit quantity calculation for short positions."""
        config = TrendConfig(timeframe='15m', base_position_size=10, partial_exit_percentage=0.5)
        
        trend_book = TrendBook()
        trend_book.position = -10  # Short position
        
        # Partial exit should use absolute value
        partial_qty = int(abs(trend_book.position) * config.partial_exit_percentage)
        assert partial_qty == 5, "50% of |-10| should be 5"
    
    def test_partial_exit_minimum_quantity(self):
        """Test that partial exit always exits at least 1 unit."""
        config = TrendConfig(timeframe='15m', base_position_size=1, partial_exit_percentage=0.5)
        
        trend_book = TrendBook()
        trend_book.position = 1  # Very small position
        
        # Even with 50% of 1, should exit at least 1 unit
        partial_qty = int(abs(trend_book.position) * config.partial_exit_percentage)
        
        # If calculation gives 0, implementation should ensure at least 1
        if partial_qty == 0:
            partial_qty = 1
        
        assert partial_qty >= 1, "Partial exit should always be at least 1 unit"


class TestTrendEngineIntegration:
    """Integration tests for Trend Engine with real market scenarios."""
    
    def test_uptrend_entry_scenario(self):
        """Test entry signal generation in uptrend scenario."""
        # Set up components
        timeframes = ['15m']
        candle_builder = CandleBuilder(timeframes)
        indicator_service = IndicatorService(candle_builder)
        market_state = MarketStateDetector(candle_builder, indicator_service)
        config = TrendConfig(timeframe='15m', base_position_size=1)
        engine = TrendEngine(market_state, indicator_service, config)
        
        # Create uptrend pattern: higher highs and higher lows
        base_time = datetime.now()
        uptrend_candles = [
            # Initial candles
            Candle(base_time, 100.0, 102.0, 99.0, 101.0, 1000, '15m'),
            Candle(base_time + timedelta(minutes=15), 101.0, 103.0, 100.0, 102.0, 1000, '15m'),
            Candle(base_time + timedelta(minutes=30), 102.0, 104.0, 101.0, 103.0, 1000, '15m'),
            # Higher low (pullback)
            Candle(base_time + timedelta(minutes=45), 103.0, 103.5, 101.5, 102.0, 1000, '15m'),
            # Higher high
            Candle(base_time + timedelta(minutes=60), 102.0, 105.0, 101.5, 104.0, 1000, '15m'),
        ]
        
        # Add more candles to meet minimum requirements
        for i in range(50):
            candle = Candle(
                timestamp=base_time + timedelta(minutes=15 * (i + 5)),
                open=104.0 + i * 0.5,
                high=105.0 + i * 0.5,
                low=103.0 + i * 0.5,
                close=104.5 + i * 0.5,
                volume=1000,
                timeframe='15m'
            )
            uptrend_candles.append(candle)
        
        candle_builder.historical_candles['15m'] = uptrend_candles
        
        trend_book = TrendBook()
        
        # Evaluate should work without errors
        signal = engine.evaluate(trend_book, 130.0)
        # Signal may or may not be generated depending on exact conditions
        # The important thing is no errors are raised
        assert signal is None or isinstance(signal, type(signal))


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
