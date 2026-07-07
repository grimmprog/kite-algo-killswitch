"""
Unit tests for OrderExecutor.

Tests cover:
- Order placement with mocked Kite API
- Order retry logic
- Order failure handling
- Trade ledger recording
- Order type selection
- Transaction type determination
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch
import time

from hybrid_trading.execution.order_executor import OrderExecutor, ExecutionConfig, LedgerEntry
from hybrid_trading.execution.models import Signal, OrderResult
from hybrid_trading.common.enums import SignalType


@pytest.fixture
def mock_kite():
    """Create a mock KiteConnect instance."""
    kite = Mock()
    kite.VARIETY_REGULAR = 'regular'
    return kite


@pytest.fixture
def config():
    """Create test execution config."""
    return ExecutionConfig(
        symbol='NIFTY24JANFUT',
        exchange='NFO',
        order_timeout=2,  # Short timeout for tests
        use_limit_orders=False,
        max_retry_attempts=3,
        retry_backoff_base=0.1  # Fast backoff for tests
    )


@pytest.fixture
def executor(mock_kite, config):
    """Create OrderExecutor with mocked Kite."""
    return OrderExecutor(mock_kite, config)


@pytest.fixture
def entry_long_signal():
    """Create a long entry signal."""
    return Signal(
        signal_type=SignalType.ENTRY_LONG,
        engine='trend',
        quantity=50,
        reason='Test long entry',
        timestamp=datetime.now(),
        price=19500.0
    )


@pytest.fixture
def entry_short_signal():
    """Create a short entry signal."""
    return Signal(
        signal_type=SignalType.ENTRY_SHORT,
        engine='trend',
        quantity=50,
        reason='Test short entry',
        timestamp=datetime.now(),
        price=19500.0
    )


@pytest.fixture
def exit_full_signal():
    """Create a full exit signal."""
    return Signal(
        signal_type=SignalType.EXIT_FULL,
        engine='trend',
        quantity=50,
        reason='Test exit',
        timestamp=datetime.now(),
        price=19550.0
    )


class TestOrderTypeSelection:
    """Test order type selection logic."""
    
    def test_entry_uses_market_by_default(self, executor, entry_long_signal):
        """Entry signals should use MARKET by default."""
        order_type = executor._select_order_type(entry_long_signal)
        assert order_type == 'MARKET'
    
    def test_entry_uses_limit_when_configured(self, mock_kite, entry_long_signal):
        """Entry signals should use LIMIT when configured."""
        config = ExecutionConfig(use_limit_orders=True)
        executor = OrderExecutor(mock_kite, config)
        
        order_type = executor._select_order_type(entry_long_signal)
        assert order_type == 'LIMIT'
    
    def test_exit_always_uses_market(self, executor, exit_full_signal):
        """Exit signals should always use MARKET."""
        order_type = executor._select_order_type(exit_full_signal)
        assert order_type == 'MARKET'
    
    def test_exit_uses_market_even_with_limit_config(self, mock_kite, exit_full_signal):
        """Exit signals should use MARKET even when LIMIT is configured."""
        config = ExecutionConfig(use_limit_orders=True)
        executor = OrderExecutor(mock_kite, config)
        
        order_type = executor._select_order_type(exit_full_signal)
        assert order_type == 'MARKET'


class TestTransactionTypeSelection:
    """Test transaction type determination."""
    
    def test_entry_long_is_buy(self, executor, entry_long_signal):
        """ENTRY_LONG should be BUY."""
        transaction_type = executor._get_transaction_type(entry_long_signal)
        assert transaction_type == 'BUY'
    
    def test_entry_short_is_sell(self, executor, entry_short_signal):
        """ENTRY_SHORT should be SELL."""
        transaction_type = executor._get_transaction_type(entry_short_signal)
        assert transaction_type == 'SELL'
    
    def test_exit_without_context_raises_error(self, executor, exit_full_signal):
        """Exit without position context should raise error."""
        with pytest.raises(ValueError, match="Cannot determine transaction type"):
            executor._get_transaction_type(exit_full_signal)
    
    def test_exit_with_override_uses_override(self, executor, exit_full_signal):
        """Exit with transaction_type override should use it."""
        executor._override_transaction_type = 'SELL'
        transaction_type = executor._get_transaction_type(exit_full_signal)
        assert transaction_type == 'SELL'


class TestLimitPriceCalculation:
    """Test limit price calculation."""
    
    def test_buy_limit_above_signal_price(self, executor, entry_long_signal):
        """BUY limit price should be above signal price."""
        limit_price = executor._calculate_limit_price(entry_long_signal, 'BUY')
        assert limit_price > entry_long_signal.price
    
    def test_sell_limit_below_signal_price(self, executor, entry_short_signal):
        """SELL limit price should be below signal price."""
        limit_price = executor._calculate_limit_price(entry_short_signal, 'SELL')
        assert limit_price < entry_short_signal.price
    
    def test_limit_price_uses_offset(self, executor, entry_long_signal):
        """Limit price should use configured offset."""
        expected_offset = executor.config.limit_order_offset_pct / 100.0
        limit_price = executor._calculate_limit_price(entry_long_signal, 'BUY')
        expected_price = round(entry_long_signal.price * (1 + expected_offset), 2)
        assert limit_price == expected_price


class TestOrderPlacement:
    """Test order placement with mocked API."""
    
    def test_successful_order_placement(self, executor, mock_kite, entry_long_signal):
        """Test successful order placement."""
        # Mock order placement
        mock_kite.place_order.return_value = 'ORDER123'
        
        # Mock order status query
        mock_kite.orders.return_value = [{
            'order_id': 'ORDER123',
            'status': 'COMPLETE',
            'filled_quantity': 50,
            'average_price': 19500.0
        }]
        
        result = executor.place_order(entry_long_signal)
        
        assert result.is_complete
        assert result.order_id == 'ORDER123'
        assert result.filled_quantity == 50
        assert result.average_price == 19500.0
    
    def test_order_rejection(self, executor, mock_kite, entry_long_signal):
        """Test order rejection handling."""
        # Mock order placement
        mock_kite.place_order.return_value = 'ORDER123'
        
        # Mock order status query
        mock_kite.orders.return_value = [{
            'order_id': 'ORDER123',
            'status': 'REJECTED',
            'filled_quantity': 0,
            'average_price': 0.0,
            'status_message': 'Insufficient margin'
        }]
        
        result = executor.place_order(entry_long_signal)
        
        assert result.is_rejected
        assert result.order_id == 'ORDER123'
        assert 'Insufficient margin' in result.message
    
    def test_order_placement_exception(self, executor, mock_kite, entry_long_signal):
        """Test order placement exception handling."""
        # Mock order placement to raise exception
        mock_kite.place_order.side_effect = Exception("Network error")
        
        result = executor.place_order(entry_long_signal)
        
        assert result.is_rejected
        assert 'Network error' in result.message
    
    def test_order_with_explicit_transaction_type(self, executor, mock_kite, exit_full_signal):
        """Test order placement with explicit transaction type."""
        # Mock order placement
        mock_kite.place_order.return_value = 'ORDER123'
        
        # Mock order status query
        mock_kite.orders.return_value = [{
            'order_id': 'ORDER123',
            'status': 'COMPLETE',
            'filled_quantity': 50,
            'average_price': 19550.0
        }]
        
        result = executor.place_order(exit_full_signal, transaction_type='SELL')
        
        assert result.is_complete
        assert result.order_id == 'ORDER123'


class TestRetryLogic:
    """Test retry logic with exponential backoff."""
    
    def test_retry_on_pending_status(self, executor, mock_kite, entry_long_signal):
        """Test retry when order is pending."""
        # Mock order placement
        mock_kite.place_order.return_value = 'ORDER123'
        
        # Mock order status query - first pending, then complete
        mock_kite.orders.side_effect = [
            [{'order_id': 'ORDER123', 'status': 'PENDING'}],
            [{'order_id': 'ORDER123', 'status': 'COMPLETE', 
              'filled_quantity': 50, 'average_price': 19500.0}]
        ]
        
        with patch('time.sleep'):  # Mock sleep to speed up test
            result = executor.place_order(entry_long_signal)
        
        assert result.is_complete
        # Note: The order is placed once, then we poll for status
        # The retry logic retries the entire order placement, not just status polling
        assert mock_kite.place_order.call_count == 1
    
    def test_max_retries_exhausted(self, executor, mock_kite, entry_long_signal):
        """Test behavior when max retries are exhausted."""
        # Mock order placement to always fail
        mock_kite.place_order.side_effect = Exception("Network error")
        
        with patch('time.sleep'):  # Mock sleep to speed up test
            result = executor.place_order(entry_long_signal)
        
        assert result.is_rejected
        assert 'Max retries' in result.message or 'Network error' in result.message
        assert mock_kite.place_order.call_count == executor.config.max_retry_attempts
    
    def test_no_retry_on_rejection(self, executor, mock_kite, entry_long_signal):
        """Test that rejected orders are not retried."""
        # Mock order placement
        mock_kite.place_order.return_value = 'ORDER123'
        
        # Mock order status query - immediate rejection
        mock_kite.orders.return_value = [{
            'order_id': 'ORDER123',
            'status': 'REJECTED',
            'filled_quantity': 0,
            'average_price': 0.0,
            'status_message': 'Invalid order'
        }]
        
        result = executor.place_order(entry_long_signal)
        
        assert result.is_rejected
        assert mock_kite.place_order.call_count == 1  # No retries


class TestTradeLedger:
    """Test trade ledger functionality."""
    
    def test_ledger_records_successful_order(self, executor, mock_kite, entry_long_signal):
        """Test that successful orders are recorded in ledger."""
        # Mock order placement
        mock_kite.place_order.return_value = 'ORDER123'
        mock_kite.orders.return_value = [{
            'order_id': 'ORDER123',
            'status': 'COMPLETE',
            'filled_quantity': 50,
            'average_price': 19500.0
        }]
        
        executor.place_order(entry_long_signal)
        
        ledger = executor.get_trade_ledger()
        assert len(ledger) == 1
        assert ledger[0].order_id == 'ORDER123'
        assert ledger[0].signal == entry_long_signal
        assert ledger[0].book == 'trend'
    
    def test_ledger_records_failed_order(self, executor, mock_kite, entry_long_signal):
        """Test that failed orders are recorded in ledger."""
        # Mock order placement to fail
        mock_kite.place_order.side_effect = Exception("Network error")
        
        executor.place_order(entry_long_signal)
        
        ledger = executor.get_trade_ledger()
        assert len(ledger) >= 1  # At least one attempt recorded
        assert ledger[-1].order_result.is_rejected
    
    def test_ledger_records_all_attempts(self, executor, mock_kite, entry_long_signal):
        """Test that all retry attempts are recorded."""
        # Mock order placement to always fail
        mock_kite.place_order.side_effect = Exception("Network error")
        
        with patch('time.sleep'):
            executor.place_order(entry_long_signal)
        
        ledger = executor.get_trade_ledger()
        assert len(ledger) == executor.config.max_retry_attempts
    
    def test_ledger_summary(self, executor, mock_kite, entry_long_signal, entry_short_signal):
        """Test ledger summary statistics."""
        # Mock successful order
        mock_kite.place_order.return_value = 'ORDER123'
        mock_kite.orders.return_value = [{
            'order_id': 'ORDER123',
            'status': 'COMPLETE',
            'filled_quantity': 50,
            'average_price': 19500.0
        }]
        
        executor.place_order(entry_long_signal)
        
        # Mock failed order
        mock_kite.place_order.side_effect = Exception("Error")
        executor.place_order(entry_short_signal)
        
        summary = executor.get_ledger_summary()
        assert summary['total_orders'] >= 2
        assert summary['completed'] >= 1
        assert summary['rejected'] >= 1


class TestBrokerPositionQuery:
    """Test broker position query."""
    
    def test_get_position_with_existing_position(self, executor, mock_kite):
        """Test querying existing position."""
        mock_kite.positions.return_value = {
            'net': [{
                'tradingsymbol': 'NIFTY24JANFUT',
                'quantity': 50
            }]
        }
        
        position = executor.get_broker_position()
        assert position == 50
    
    def test_get_position_with_no_position(self, executor, mock_kite):
        """Test querying when no position exists."""
        mock_kite.positions.return_value = {
            'net': []
        }
        
        position = executor.get_broker_position()
        assert position == 0
    
    def test_get_position_with_different_symbol(self, executor, mock_kite):
        """Test querying position for different symbol."""
        mock_kite.positions.return_value = {
            'net': [{
                'tradingsymbol': 'BANKNIFTY24JANFUT',
                'quantity': 25
            }]
        }
        
        position = executor.get_broker_position()
        assert position == 0  # Our symbol not found
    
    def test_get_position_api_error(self, executor, mock_kite):
        """Test position query with API error."""
        mock_kite.positions.side_effect = Exception("API error")
        
        with pytest.raises(Exception, match="API error"):
            executor.get_broker_position()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
