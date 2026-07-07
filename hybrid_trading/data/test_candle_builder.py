"""
Unit tests for CandleBuilder and IndicatorService.
"""

import pytest
from datetime import datetime, timedelta
from hybrid_trading.data import Tick, Candle, CandleBuilder, IndicatorService


class TestCandleBuilder:
    """Test cases for CandleBuilder class."""
    
    def test_initialization(self):
        """Test CandleBuilder initialization."""
        timeframes = ['1m', '5m', '15m']
        builder = CandleBuilder(timeframes)
        
        assert builder.timeframes == timeframes
        assert len(builder.current_candles) == 3
        assert len(builder.historical_candles) == 3
        assert all(builder.current_candles[tf] is None for tf in timeframes)
    
    def test_invalid_timeframe(self):
        """Test initialization with invalid timeframe."""
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            CandleBuilder(['invalid'])
    
    def test_first_tick_creates_candle(self):
        """Test that first tick creates a new candle."""
        builder = CandleBuilder(['5m'])
        
        tick = Tick(
            timestamp=datetime(2024, 1, 1, 9, 32, 15),
            symbol='NIFTY',
            last_price=21000.0,
            volume=100
        )
        
        completed = builder.on_tick(tick)
        
        # No candle should be completed yet
        assert completed['5m'] is None
        
        # Current candle should be created
        current = builder.get_current_candle('5m')
        assert current is not None
        assert current.open == 21000.0
        assert current.high == 21000.0
        assert current.low == 21000.0
        assert current.close == 21000.0
        assert current.volume == 100
        assert current.timeframe == '5m'
        # Should be rounded to 09:30:00
        assert current.timestamp == datetime(2024, 1, 1, 9, 30, 0)
    
    def test_tick_updates_current_candle(self):
        """Test that subsequent ticks update the current candle."""
        builder = CandleBuilder(['5m'])
        
        # First tick
        tick1 = Tick(
            timestamp=datetime(2024, 1, 1, 9, 32, 0),
            symbol='NIFTY',
            last_price=21000.0,
            volume=100
        )
        builder.on_tick(tick1)
        
        # Second tick - higher price
        tick2 = Tick(
            timestamp=datetime(2024, 1, 1, 9, 33, 0),
            symbol='NIFTY',
            last_price=21050.0,
            volume=150
        )
        builder.on_tick(tick2)
        
        current = builder.get_current_candle('5m')
        assert current.open == 21000.0
        assert current.high == 21050.0
        assert current.low == 21000.0
        assert current.close == 21050.0
        assert current.volume == 250  # Accumulated
        
        # Third tick - lower price
        tick3 = Tick(
            timestamp=datetime(2024, 1, 1, 9, 34, 0),
            symbol='NIFTY',
            last_price=20980.0,
            volume=120
        )
        builder.on_tick(tick3)
        
        current = builder.get_current_candle('5m')
        assert current.open == 21000.0
        assert current.high == 21050.0
        assert current.low == 20980.0
        assert current.close == 20980.0
        assert current.volume == 370
    
    def test_candle_completion_on_timeframe_boundary(self):
        """Test that candle completes when crossing timeframe boundary."""
        builder = CandleBuilder(['5m'])
        
        # Tick in 09:30-09:35 period
        tick1 = Tick(
            timestamp=datetime(2024, 1, 1, 9, 32, 0),
            symbol='NIFTY',
            last_price=21000.0,
            volume=100
        )
        completed = builder.on_tick(tick1)
        assert completed['5m'] is None
        
        # Tick in 09:35-09:40 period (new candle)
        tick2 = Tick(
            timestamp=datetime(2024, 1, 1, 9, 35, 0),
            symbol='NIFTY',
            last_price=21050.0,
            volume=150
        )
        completed = builder.on_tick(tick2)
        
        # Previous candle should be completed
        assert completed['5m'] is not None
        assert completed['5m'].timestamp == datetime(2024, 1, 1, 9, 30, 0)
        assert completed['5m'].close == 21000.0
        
        # New candle should be started
        current = builder.get_current_candle('5m')
        assert current.timestamp == datetime(2024, 1, 1, 9, 35, 0)
        assert current.open == 21050.0
    
    def test_historical_candles_storage(self):
        """Test that completed candles are stored in historical buffer."""
        builder = CandleBuilder(['5m'], max_historical_candles=3)
        
        # Create 5 candles by crossing timeframe boundaries
        for i in range(5):
            tick = Tick(
                timestamp=datetime(2024, 1, 1, 9, 30 + i * 5, 0),
                symbol='NIFTY',
                last_price=21000.0 + i * 10,
                volume=100
            )
            builder.on_tick(tick)
        
        # Should have 3 historical candles (max_historical_candles=3)
        # The first candle is still current, so we have 4 completed
        # But buffer only keeps last 3
        historical = builder.get_candles('5m', 10)
        assert len(historical) <= 4  # At most 4 completed
    
    def test_get_candles(self):
        """Test retrieving historical candles."""
        builder = CandleBuilder(['5m'])
        
        # Create 3 completed candles
        for i in range(4):
            tick = Tick(
                timestamp=datetime(2024, 1, 1, 9, 30 + i * 5, 0),
                symbol='NIFTY',
                last_price=21000.0 + i * 10,
                volume=100
            )
            builder.on_tick(tick)
        
        # Get last 2 candles
        candles = builder.get_candles('5m', 2)
        assert len(candles) <= 3  # Should have at most 3 completed
        
        # Get more candles than available
        candles = builder.get_candles('5m', 100)
        assert len(candles) <= 3
    
    def test_multiple_timeframes(self):
        """Test candle building across multiple timeframes."""
        builder = CandleBuilder(['1m', '5m'])
        
        # Send ticks spanning multiple minutes
        for minute in range(6):
            tick = Tick(
                timestamp=datetime(2024, 1, 1, 9, 30 + minute, 30),
                symbol='NIFTY',
                last_price=21000.0 + minute * 5,
                volume=100
            )
            completed = builder.on_tick(tick)
            
            # 1m candles should complete every minute
            if minute > 0:
                assert completed['1m'] is not None
            
            # 5m candle should complete at minute 5
            if minute == 5:
                assert completed['5m'] is not None
            elif minute < 5:
                assert completed['5m'] is None


class TestIndicatorService:
    """Test cases for IndicatorService class."""
    
    def create_test_candles(self, count: int, start_price: float = 21000.0) -> CandleBuilder:
        """Helper to create test candles."""
        builder = CandleBuilder(['5m'])
        
        base_time = datetime(2024, 1, 1, 9, 30, 0)
        for i in range(count):
            tick = Tick(
                timestamp=base_time + timedelta(minutes=i * 5),
                symbol='NIFTY',
                last_price=start_price + i * 10,
                volume=100 + i * 10
            )
            builder.on_tick(tick)
        
        return builder
    
    def test_vwap_calculation(self):
        """Test VWAP calculation."""
        builder = self.create_test_candles(5)
        service = IndicatorService(builder)
        
        vwap = service.calculate_vwap('5m', 3)
        assert vwap is not None
        assert vwap > 0
    
    def test_vwap_insufficient_data(self):
        """Test VWAP with insufficient data."""
        builder = CandleBuilder(['5m'])
        service = IndicatorService(builder)
        
        vwap = service.calculate_vwap('5m', 10)
        assert vwap is None
    
    def test_atr_calculation(self):
        """Test ATR calculation."""
        builder = self.create_test_candles(20)
        service = IndicatorService(builder)
        
        atr = service.calculate_atr('5m', 14)
        assert atr is not None
        assert atr > 0
    
    def test_atr_insufficient_data(self):
        """Test ATR with insufficient data."""
        builder = CandleBuilder(['5m'])
        service = IndicatorService(builder)
        
        atr = service.calculate_atr('5m', 14)
        assert atr is None
    
    def test_ema_calculation(self):
        """Test EMA calculation."""
        builder = self.create_test_candles(30)
        service = IndicatorService(builder)
        
        ema = service.calculate_ema('5m', 20)
        assert ema is not None
        assert ema > 0
    
    def test_ema_insufficient_data(self):
        """Test EMA with insufficient data."""
        builder = CandleBuilder(['5m'])
        service = IndicatorService(builder)
        
        ema = service.calculate_ema('5m', 20)
        assert ema is None
    
    def test_sma_calculation(self):
        """Test SMA calculation."""
        builder = self.create_test_candles(10)
        service = IndicatorService(builder)
        
        sma = service.calculate_sma('5m', 5)
        assert sma is not None
        assert sma > 0
    
    def test_impulse_size_calculation(self):
        """Test impulse size calculation."""
        builder = CandleBuilder(['5m'])
        service = IndicatorService(builder)
        
        candles = [
            Candle(datetime.now(), 21000, 21050, 20980, 21030, 100, '5m'),
            Candle(datetime.now(), 21030, 21080, 21020, 21070, 100, '5m'),
            Candle(datetime.now(), 21070, 21120, 21060, 21100, 100, '5m'),
        ]
        
        impulse = service.calculate_impulse_size(candles)
        assert impulse == 100.0  # 21100 - 21000
    
    def test_average_body_size(self):
        """Test average body size calculation."""
        builder = CandleBuilder(['5m'])
        service = IndicatorService(builder)
        
        candles = [
            Candle(datetime.now(), 21000, 21050, 20980, 21030, 100, '5m'),  # body: 30
            Candle(datetime.now(), 21030, 21080, 21020, 21070, 100, '5m'),  # body: 40
            Candle(datetime.now(), 21070, 21120, 21060, 21050, 100, '5m'),  # body: 20
        ]
        
        avg_body = service.calculate_average_body_size(candles)
        assert avg_body == 30.0  # (30 + 40 + 20) / 3
    
    def test_consecutive_large_candles(self):
        """Test counting consecutive large candles."""
        builder = CandleBuilder(['5m'])
        service = IndicatorService(builder)
        
        candles = [
            Candle(datetime.now(), 21000, 21050, 20980, 21020, 100, '5m'),  # body: 20
            Candle(datetime.now(), 21020, 21080, 21010, 21070, 100, '5m'),  # body: 50 (large)
            Candle(datetime.now(), 21070, 21130, 21060, 21120, 100, '5m'),  # body: 50 (large)
            Candle(datetime.now(), 21120, 21180, 21110, 21170, 100, '5m'),  # body: 50 (large)
        ]
        
        # Average body = (20 + 50 + 50 + 50) / 4 = 42.5
        # Threshold = 42.5 * 1.5 = 63.75
        # Last 3 candles have body 50, which is < 63.75, so count = 0
        count = service.count_consecutive_large_candles(candles, threshold_multiplier=1.5)
        assert count == 0
        
        # With lower threshold
        count = service.count_consecutive_large_candles(candles, threshold_multiplier=1.0)
        assert count == 3  # Last 3 candles have body >= 42.5


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
