"""
Unit tests for Position Manager components.

Tests TrendBook, MRBook, and PositionManager classes.
"""

import pytest
from datetime import datetime

from .position_manager import TrendBook, MRBook, PositionManager
from .models import MRTrade, Signal
from ..common.enums import SignalType


class TestTrendBook:
    """Unit tests for TrendBook class."""
    
    def test_initial_state(self):
        """Test TrendBook starts with zero position."""
        book = TrendBook()
        assert book.position == 0
        assert book.avg_entry_price == 0.0
        assert len(book.trades) == 0
    
    def test_add_long_position(self):
        """Test adding a long position."""
        book = TrendBook()
        book.add_position(50, 18000.0)
        
        assert book.position == 50
        assert book.avg_entry_price == 18000.0
        assert len(book.trades) == 1
    
    def test_add_short_position(self):
        """Test adding a short position."""
        book = TrendBook()
        book.add_position(-50, 18000.0)
        
        assert book.position == -50
        assert book.avg_entry_price == 18000.0
        assert len(book.trades) == 1
    
    def test_add_to_existing_long_position(self):
        """Test adding to an existing long position updates average price."""
        book = TrendBook()
        book.add_position(50, 18000.0)
        book.add_position(50, 18100.0)
        
        assert book.position == 100
        # Average: (50*18000 + 50*18100) / 100 = 18050
        assert book.avg_entry_price == 18050.0
        assert len(book.trades) == 2
    
    def test_add_to_existing_short_position(self):
        """Test adding to an existing short position updates average price."""
        book = TrendBook()
        book.add_position(-50, 18000.0)
        book.add_position(-50, 17900.0)
        
        assert book.position == -100
        # Average: (50*18000 + 50*17900) / 100 = 17950
        assert book.avg_entry_price == 17950.0
        assert len(book.trades) == 2
    
    def test_reduce_long_position(self):
        """Test reducing a long position."""
        book = TrendBook()
        book.add_position(100, 18000.0)
        book.reduce_position(50, 18100.0)
        
        assert book.position == 50
        assert book.avg_entry_price == 18000.0  # Avg price unchanged
        assert len(book.trades) == 2
    
    def test_reduce_short_position(self):
        """Test reducing a short position."""
        book = TrendBook()
        book.add_position(-100, 18000.0)
        book.reduce_position(50, 17900.0)
        
        assert book.position == -50
        assert book.avg_entry_price == 18000.0  # Avg price unchanged
        assert len(book.trades) == 2
    
    def test_close_long_position_fully(self):
        """Test closing a long position fully resets avg price."""
        book = TrendBook()
        book.add_position(50, 18000.0)
        book.reduce_position(50, 18100.0)
        
        assert book.position == 0
        assert book.avg_entry_price == 0.0
        assert len(book.trades) == 2
    
    def test_close_short_position_fully(self):
        """Test closing a short position fully resets avg price."""
        book = TrendBook()
        book.add_position(-50, 18000.0)
        book.reduce_position(50, 17900.0)
        
        assert book.position == 0
        assert book.avg_entry_price == 0.0
        assert len(book.trades) == 2
    
    def test_add_position_zero_quantity_raises_error(self):
        """Test adding zero quantity raises ValueError."""
        book = TrendBook()
        with pytest.raises(ValueError, match="Cannot add zero quantity"):
            book.add_position(0, 18000.0)
    
    def test_add_position_invalid_price_raises_error(self):
        """Test adding position with invalid price raises ValueError."""
        book = TrendBook()
        with pytest.raises(ValueError, match="Invalid price"):
            book.add_position(50, -18000.0)
    
    def test_reduce_position_zero_quantity_raises_error(self):
        """Test reducing by zero quantity raises ValueError."""
        book = TrendBook()
        book.add_position(50, 18000.0)
        with pytest.raises(ValueError, match="Quantity must be positive"):
            book.reduce_position(0, 18100.0)
    
    def test_reduce_position_exceeds_current_raises_error(self):
        """Test reducing more than current position raises ValueError."""
        book = TrendBook()
        book.add_position(50, 18000.0)
        with pytest.raises(ValueError, match="Cannot reduce"):
            book.reduce_position(100, 18100.0)
    
    def test_unrealized_pnl_long_position(self):
        """Test unrealized P&L calculation for long position."""
        book = TrendBook()
        book.add_position(50, 18000.0)
        
        # Price goes up
        pnl = book.get_unrealized_pnl(18100.0)
        assert pnl == 50 * (18100.0 - 18000.0)
        assert pnl == 5000.0
        
        # Price goes down
        pnl = book.get_unrealized_pnl(17900.0)
        assert pnl == 50 * (17900.0 - 18000.0)
        assert pnl == -5000.0
    
    def test_unrealized_pnl_short_position(self):
        """Test unrealized P&L calculation for short position."""
        book = TrendBook()
        book.add_position(-50, 18000.0)
        
        # Price goes down (profit for short)
        pnl = book.get_unrealized_pnl(17900.0)
        assert pnl == 50 * (18000.0 - 17900.0)
        assert pnl == 5000.0
        
        # Price goes up (loss for short)
        pnl = book.get_unrealized_pnl(18100.0)
        assert pnl == 50 * (18000.0 - 18100.0)
        assert pnl == -5000.0
    
    def test_unrealized_pnl_zero_position(self):
        """Test unrealized P&L is zero when position is zero."""
        book = TrendBook()
        pnl = book.get_unrealized_pnl(18000.0)
        assert pnl == 0.0


class TestMRBook:
    """Unit tests for MRBook class."""
    
    def test_initial_state(self):
        """Test MRBook starts with zero position."""
        book = MRBook()
        assert book.position == 0
        assert len(book.active_trades) == 0
    
    def test_add_long_trade(self):
        """Test adding a long MR trade."""
        book = MRBook()
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=18100.0,
            quantity=15,
            direction='long',
            impulse_start=18000.0,
            impulse_end=18100.0
        )
        book.add_trade(trade)
        
        assert book.position == 15
        assert len(book.active_trades) == 1
        assert book.active_trades[0] == trade
    
    def test_add_short_trade(self):
        """Test adding a short MR trade."""
        book = MRBook()
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=17900.0,
            quantity=15,
            direction='short',
            impulse_start=18000.0,
            impulse_end=17900.0
        )
        book.add_trade(trade)
        
        assert book.position == -15
        assert len(book.active_trades) == 1
        assert book.active_trades[0] == trade
    
    def test_add_multiple_trades(self):
        """Test adding multiple MR trades."""
        book = MRBook()
        
        trade1 = MRTrade(
            entry_time=datetime.now(),
            entry_price=18100.0,
            quantity=15,
            direction='long',
            impulse_start=18000.0,
            impulse_end=18100.0
        )
        trade2 = MRTrade(
            entry_time=datetime.now(),
            entry_price=18150.0,
            quantity=10,
            direction='long',
            impulse_start=18000.0,
            impulse_end=18150.0
        )
        
        book.add_trade(trade1)
        book.add_trade(trade2)
        
        assert book.position == 25
        assert len(book.active_trades) == 2
    
    def test_close_long_trade(self):
        """Test closing a long MR trade."""
        book = MRBook()
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=18100.0,
            quantity=15,
            direction='long',
            impulse_start=18000.0,
            impulse_end=18100.0
        )
        book.add_trade(trade)
        book.close_trade(trade, 18050.0)
        
        assert book.position == 0
        assert len(book.active_trades) == 0
    
    def test_close_short_trade(self):
        """Test closing a short MR trade."""
        book = MRBook()
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=17900.0,
            quantity=15,
            direction='short',
            impulse_start=18000.0,
            impulse_end=17900.0
        )
        book.add_trade(trade)
        book.close_trade(trade, 17950.0)
        
        assert book.position == 0
        assert len(book.active_trades) == 0
    
    def test_close_trade_not_in_active_raises_error(self):
        """Test closing a trade not in active trades raises ValueError."""
        book = MRBook()
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=18100.0,
            quantity=15,
            direction='long',
            impulse_start=18000.0,
            impulse_end=18100.0
        )
        
        with pytest.raises(ValueError, match="Trade not found"):
            book.close_trade(trade, 18050.0)
    
    def test_add_trade_invalid_type_raises_error(self):
        """Test adding non-MRTrade object raises TypeError."""
        book = MRBook()
        with pytest.raises(TypeError, match="Expected MRTrade"):
            book.add_trade("not a trade")
    
    def test_unrealized_pnl_long_trades(self):
        """Test unrealized P&L calculation for long MR trades."""
        book = MRBook()
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=18100.0,
            quantity=15,
            direction='long',
            impulse_start=18000.0,
            impulse_end=18100.0
        )
        book.add_trade(trade)
        
        # Price goes up
        pnl = book.get_unrealized_pnl(18150.0)
        assert pnl == 15 * (18150.0 - 18100.0)
        assert pnl == 750.0
        
        # Price goes down
        pnl = book.get_unrealized_pnl(18050.0)
        assert pnl == 15 * (18050.0 - 18100.0)
        assert pnl == -750.0
    
    def test_unrealized_pnl_short_trades(self):
        """Test unrealized P&L calculation for short MR trades."""
        book = MRBook()
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=17900.0,
            quantity=15,
            direction='short',
            impulse_start=18000.0,
            impulse_end=17900.0
        )
        book.add_trade(trade)
        
        # Price goes down (profit for short)
        pnl = book.get_unrealized_pnl(17850.0)
        assert pnl == 15 * (17900.0 - 17850.0)
        assert pnl == 750.0
        
        # Price goes up (loss for short)
        pnl = book.get_unrealized_pnl(17950.0)
        assert pnl == 15 * (17900.0 - 17950.0)
        assert pnl == -750.0
    
    def test_unrealized_pnl_multiple_trades(self):
        """Test unrealized P&L calculation with multiple trades."""
        book = MRBook()
        
        trade1 = MRTrade(
            entry_time=datetime.now(),
            entry_price=18100.0,
            quantity=15,
            direction='long',
            impulse_start=18000.0,
            impulse_end=18100.0
        )
        trade2 = MRTrade(
            entry_time=datetime.now(),
            entry_price=18150.0,
            quantity=10,
            direction='long',
            impulse_start=18000.0,
            impulse_end=18150.0
        )
        
        book.add_trade(trade1)
        book.add_trade(trade2)
        
        # Current price 18120
        pnl = book.get_unrealized_pnl(18120.0)
        expected = 15 * (18120.0 - 18100.0) + 10 * (18120.0 - 18150.0)
        assert pnl == expected
        assert pnl == 300.0 - 300.0
        assert pnl == 0.0


class TestPositionManager:
    """Unit tests for PositionManager class."""
    
    def test_initial_state(self):
        """Test PositionManager starts with zero net position."""
        pm = PositionManager()
        assert pm.get_net_position() == 0
        assert pm.trend_book.position == 0
        assert pm.mr_book.position == 0
    
    def test_net_position_trend_only(self):
        """Test net position with only trend position."""
        pm = PositionManager()
        pm.trend_book.add_position(50, 18000.0)
        
        assert pm.get_net_position() == 50
    
    def test_net_position_trend_and_mr(self):
        """Test net position with both trend and MR positions."""
        pm = PositionManager()
        pm.trend_book.add_position(50, 18000.0)
        
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=18100.0,
            quantity=15,
            direction='short',
            impulse_start=18000.0,
            impulse_end=18100.0
        )
        pm.mr_book.add_trade(trade)
        
        # Net: 50 (long trend) - 15 (short MR) = 35
        assert pm.get_net_position() == 35
    
    def test_can_enter_mr_position_no_trend_position(self):
        """Test MR entry rejected when no trend position exists."""
        pm = PositionManager()
        signal = Signal(
            signal_type=SignalType.ENTRY_SHORT,
            engine='mr',
            quantity=15,
            reason='Test',
            timestamp=datetime.now(),
            price=18100.0
        )
        
        assert pm.can_enter_mr_position(signal) is False
    
    def test_can_enter_mr_position_exceeds_30_percent(self):
        """Test MR entry rejected when quantity exceeds 30% of trend."""
        pm = PositionManager()
        pm.trend_book.add_position(50, 18000.0)
        
        signal = Signal(
            signal_type=SignalType.ENTRY_SHORT,
            engine='mr',
            quantity=20,  # 40% of 50
            reason='Test',
            timestamp=datetime.now(),
            price=18100.0
        )
        
        assert pm.can_enter_mr_position(signal) is False
    
    def test_can_enter_mr_position_would_flip_net(self):
        """Test MR entry rejected when would flip net position."""
        pm = PositionManager()
        pm.trend_book.add_position(50, 18000.0)
        
        signal = Signal(
            signal_type=SignalType.ENTRY_SHORT,
            engine='mr',
            quantity=15,
            reason='Test',
            timestamp=datetime.now(),
            price=18100.0
        )
        
        # First MR entry OK
        assert pm.can_enter_mr_position(signal) is True
        
        # Add the MR trade
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=18100.0,
            quantity=15,
            direction='short',
            impulse_start=18000.0,
            impulse_end=18100.0
        )
        pm.mr_book.add_trade(trade)
        
        # Net is now 35 (50 - 15)
        # Another 15 short would make it 20
        # Another 15 after that would make it 5
        # Another 15 would flip to -10 (REJECTED)
        
        signal2 = Signal(
            signal_type=SignalType.ENTRY_SHORT,
            engine='mr',
            quantity=15,
            reason='Test',
            timestamp=datetime.now(),
            price=18150.0
        )
        assert pm.can_enter_mr_position(signal2) is True
        
        pm.mr_book.add_trade(MRTrade(
            entry_time=datetime.now(),
            entry_price=18150.0,
            quantity=15,
            direction='short',
            impulse_start=18000.0,
            impulse_end=18150.0
        ))
        
        # Net is now 20 (50 - 30)
        signal3 = Signal(
            signal_type=SignalType.ENTRY_SHORT,
            engine='mr',
            quantity=15,
            reason='Test',
            timestamp=datetime.now(),
            price=18200.0
        )
        assert pm.can_enter_mr_position(signal3) is True
        
        pm.mr_book.add_trade(MRTrade(
            entry_time=datetime.now(),
            entry_price=18200.0,
            quantity=15,
            direction='short',
            impulse_start=18000.0,
            impulse_end=18200.0
        ))
        
        # Net is now 5 (50 - 45)
        # Another 15 would flip to -10
        signal4 = Signal(
            signal_type=SignalType.ENTRY_SHORT,
            engine='mr',
            quantity=15,
            reason='Test',
            timestamp=datetime.now(),
            price=18250.0
        )
        assert pm.can_enter_mr_position(signal4) is False
    
    def test_can_enter_mr_position_exceeds_max_net(self):
        """Test MR entry rejected when would exceed max net position."""
        pm = PositionManager()
        pm.trend_book.add_position(95, 18000.0)
        
        signal = Signal(
            signal_type=SignalType.ENTRY_LONG,
            engine='mr',
            quantity=10,
            reason='Test',
            timestamp=datetime.now(),
            price=17900.0
        )
        
        # Would make net position 105, exceeding default max of 100
        assert pm.can_enter_mr_position(signal, max_net_position=100) is False
    
    def test_can_enter_mr_position_valid(self):
        """Test MR entry allowed when all constraints satisfied."""
        pm = PositionManager()
        pm.trend_book.add_position(50, 18000.0)
        
        signal = Signal(
            signal_type=SignalType.ENTRY_SHORT,
            engine='mr',
            quantity=15,  # 30% of 50
            reason='Test',
            timestamp=datetime.now(),
            price=18100.0
        )
        
        assert pm.can_enter_mr_position(signal) is True
    
    def test_can_enter_mr_position_invalid_signal_engine(self):
        """Test validation raises error for non-MR signal."""
        pm = PositionManager()
        signal = Signal(
            signal_type=SignalType.ENTRY_LONG,
            engine='trend',
            quantity=50,
            reason='Test',
            timestamp=datetime.now(),
            price=18000.0
        )
        
        with pytest.raises(ValueError, match="Expected MR signal"):
            pm.can_enter_mr_position(signal)
    
    def test_can_enter_mr_position_invalid_signal_type(self):
        """Test validation raises error for non-entry signal."""
        pm = PositionManager()
        signal = Signal(
            signal_type=SignalType.EXIT_FULL,
            engine='mr',
            quantity=15,
            reason='Test',
            timestamp=datetime.now(),
            price=18100.0
        )
        
        with pytest.raises(ValueError, match="Expected entry signal"):
            pm.can_enter_mr_position(signal)
    
    def test_reconcile_position_no_executor(self):
        """Test reconciliation returns True when no executor configured."""
        pm = PositionManager()
        assert pm.reconcile_position() is True
    
    def test_reconcile_position_no_symbol(self):
        """Test reconciliation returns True when no symbol provided."""
        class MockExecutor:
            def get_broker_position(self, symbol):
                return 0
        
        pm = PositionManager(order_executor=MockExecutor())
        assert pm.reconcile_position() is True
    
    def test_reconcile_position_match(self):
        """Test reconciliation succeeds when positions match."""
        class MockExecutor:
            def get_broker_position(self, symbol):
                return 50
        
        pm = PositionManager(order_executor=MockExecutor())
        pm.trend_book.add_position(50, 18000.0)
        
        assert pm.reconcile_position(symbol='NIFTY24JANFUT') is True
    
    def test_reconcile_position_mismatch(self):
        """Test reconciliation detects mismatch."""
        class MockExecutor:
            def get_broker_position(self, symbol):
                return 60  # Broker shows 60, but we expect 50
        
        pm = PositionManager(order_executor=MockExecutor())
        pm.trend_book.add_position(50, 18000.0)
        
        assert pm.reconcile_position(symbol='NIFTY24JANFUT') is False
    
    def test_reconcile_position_with_mr_trades(self):
        """Test reconciliation with both trend and MR positions."""
        class MockExecutor:
            def get_broker_position(self, symbol):
                return 35  # 50 (trend) - 15 (MR)
        
        pm = PositionManager(order_executor=MockExecutor())
        pm.trend_book.add_position(50, 18000.0)
        
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=18100.0,
            quantity=15,
            direction='short',
            impulse_start=18000.0,
            impulse_end=18100.0
        )
        pm.mr_book.add_trade(trade)
        
        assert pm.reconcile_position(symbol='NIFTY24JANFUT') is True
    
    def test_reconcile_position_executor_error(self):
        """Test reconciliation handles executor errors gracefully."""
        class MockExecutor:
            def get_broker_position(self, symbol):
                raise Exception("API error")
        
        pm = PositionManager(order_executor=MockExecutor())
        pm.trend_book.add_position(50, 18000.0)
        
        # Should return False on error, not raise exception
        assert pm.reconcile_position(symbol='NIFTY24JANFUT') is False
    
    def test_total_unrealized_pnl(self):
        """Test total unrealized P&L across both books."""
        pm = PositionManager()
        pm.trend_book.add_position(50, 18000.0)
        
        trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=18100.0,
            quantity=15,
            direction='short',
            impulse_start=18000.0,
            impulse_end=18100.0
        )
        pm.mr_book.add_trade(trade)
        
        # Current price 18050
        # Trend P&L: 50 * (18050 - 18000) = 2500
        # MR P&L: 15 * (18100 - 18050) = 750
        # Total: 3250
        total_pnl = pm.get_total_unrealized_pnl(18050.0)
        assert total_pnl == 3250.0
