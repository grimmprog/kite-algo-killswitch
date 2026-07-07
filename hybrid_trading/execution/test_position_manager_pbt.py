"""
Property-based tests for Position Manager components.

Uses Hypothesis to verify universal correctness properties across all inputs.
"""

import pytest
from datetime import datetime
from hypothesis import given, strategies as st, settings, assume

from .position_manager import TrendBook, MRBook, PositionManager
from .models import MRTrade, Signal
from ..common.enums import SignalType


# Strategies for generating test data
@st.composite
def mr_trade_strategy(draw):
    """Generate valid MRTrade objects."""
    entry_price = draw(st.floats(min_value=10000.0, max_value=30000.0))
    impulse_start = draw(st.floats(min_value=10000.0, max_value=30000.0))
    
    # Ensure impulse_end is different from impulse_start
    impulse_end = draw(st.floats(min_value=10000.0, max_value=30000.0))
    assume(abs(impulse_end - impulse_start) > 1.0)
    
    return MRTrade(
        entry_time=datetime.now(),
        entry_price=entry_price,
        quantity=draw(st.integers(min_value=1, max_value=50)),
        direction=draw(st.sampled_from(['long', 'short'])),
        impulse_start=impulse_start,
        impulse_end=impulse_end,
        candles_held=draw(st.integers(min_value=0, max_value=10))
    )


# Feature: hybrid-trading-system, Property 10: Net Position Calculation
@given(
    trend_position=st.integers(min_value=-100, max_value=100),
    mr_position=st.integers(min_value=-50, max_value=50)
)
@settings(max_examples=100)
def test_property_net_position_calculation(trend_position, mr_position):
    """
    Property 10: Net Position Calculation
    
    For any state of Trend_Book and MR_Book, the net position reported to the 
    broker should always equal the sum of Trend_Book.position + MR_Book.position.
    
    Validates: Requirements 4.2
    """
    pm = PositionManager()
    
    # Set positions directly (simulating various states)
    pm.trend_book.position = trend_position
    pm.mr_book.position = mr_position
    
    # Property: Net position must equal sum of both books
    net_position = pm.get_net_position()
    expected_net = trend_position + mr_position
    
    assert net_position == expected_net, (
        f"Net position {net_position} does not equal sum of books {expected_net} "
        f"(trend={trend_position}, mr={mr_position})"
    )


# Feature: hybrid-trading-system, Property 11: Position Sizing Constraints
@given(
    base_position_size=st.integers(min_value=10, max_value=200),
    mr_quantity=st.integers(min_value=1, max_value=100)
)
@settings(max_examples=100)
def test_property_position_sizing_constraints(base_position_size, mr_quantity):
    """
    Property 11: Position Sizing Constraints
    
    For any position sizing decision, trend positions should use 100% of base size 
    AND mean reversion positions should use maximum 30% of current trend position size.
    
    Validates: Requirements 4.3, 4.4
    """
    pm = PositionManager()
    
    # Trend position uses 100% of base size
    pm.trend_book.position = base_position_size
    
    # Calculate max allowed MR size (30% of trend position)
    max_mr_size = int(abs(base_position_size) * 0.3)
    
    # Create MR entry signal
    signal = Signal(
        signal_type=SignalType.ENTRY_SHORT,
        engine='mr',
        quantity=mr_quantity,
        reason='Test',
        timestamp=datetime.now(),
        price=18000.0
    )
    
    # Property: MR entry should be rejected if quantity exceeds 30% of trend
    can_enter = pm.can_enter_mr_position(signal)
    
    if mr_quantity > max_mr_size:
        assert can_enter is False, (
            f"MR entry with quantity {mr_quantity} should be rejected "
            f"(max allowed: {max_mr_size}, 30% of {base_position_size})"
        )
    else:
        # Other constraints might still reject, but size constraint should pass
        # We can't assert True here because other constraints might fail
        pass


# Feature: hybrid-trading-system, Property 12: Net Position Direction Preservation
@given(
    trend_position=st.integers(min_value=-100, max_value=100).filter(lambda x: x != 0),
    mr_quantity=st.integers(min_value=1, max_value=50)
)
@settings(max_examples=100)
def test_property_net_position_direction_preservation(trend_position, mr_quantity):
    """
    Property 12: Net Position Direction Preservation
    
    For any MR entry signal, if executing the signal would cause the net position 
    to flip against the trend direction (positive to negative or vice versa), 
    the Position_Manager should reject the entry.
    
    Validates: Requirements 4.5
    """
    pm = PositionManager()
    pm.trend_book.position = trend_position
    
    # Determine signal type based on trend direction
    # For long trend, MR should be short (counter-trend)
    # For short trend, MR should be long (counter-trend)
    if trend_position > 0:
        signal_type = SignalType.ENTRY_SHORT
        net_after = trend_position - mr_quantity
    else:
        signal_type = SignalType.ENTRY_LONG
        net_after = trend_position + mr_quantity
    
    signal = Signal(
        signal_type=signal_type,
        engine='mr',
        quantity=mr_quantity,
        reason='Test',
        timestamp=datetime.now(),
        price=18000.0
    )
    
    can_enter = pm.can_enter_mr_position(signal)
    
    # Property: If net position would flip (cross zero), entry must be rejected
    trend_is_positive = trend_position > 0
    net_would_flip = (trend_is_positive and net_after <= 0) or (not trend_is_positive and net_after >= 0)
    
    if net_would_flip:
        assert can_enter is False, (
            f"MR entry should be rejected: would flip net position from {trend_position} to {net_after}"
        )


# Feature: hybrid-trading-system, Property 13: Position Reconciliation
@given(
    trend_position=st.integers(min_value=-100, max_value=100),
    mr_position=st.integers(min_value=-50, max_value=50),
    broker_position=st.integers(min_value=-150, max_value=150)
)
@settings(max_examples=100)
def test_property_position_reconciliation(trend_position, mr_position, broker_position):
    """
    Property 13: Position Reconciliation
    
    For any order execution, the Position_Manager should reconcile expected net 
    quantity against actual broker-reported net quantity, and if a discrepancy 
    exists, should log it and trigger an alert.
    
    Validates: Requirements 4.7, 4.8
    """
    class MockExecutor:
        def __init__(self, broker_pos):
            self.broker_pos = broker_pos
        
        def get_broker_position(self, symbol):
            return self.broker_pos
    
    pm = PositionManager(order_executor=MockExecutor(broker_position))
    pm.trend_book.position = trend_position
    pm.mr_book.position = mr_position
    
    expected_net = trend_position + mr_position
    
    # Reconcile positions
    result = pm.reconcile_position(symbol='TEST')
    
    # Property: Reconciliation should return True if positions match, False otherwise
    if expected_net == broker_position:
        assert result is True, (
            f"Reconciliation should succeed when positions match "
            f"(expected={expected_net}, broker={broker_position})"
        )
    else:
        assert result is False, (
            f"Reconciliation should fail when positions mismatch "
            f"(expected={expected_net}, broker={broker_position})"
        )


# Additional property test: MR trades maintain correct position sum
@given(
    trades=st.lists(mr_trade_strategy(), min_size=0, max_size=10)
)
@settings(max_examples=100)
def test_property_mr_book_position_sum(trades):
    """
    Property: MR Book Position Sum
    
    For any sequence of MR trades added to MRBook, the net position should 
    always equal the sum of all active trade quantities (with direction).
    """
    book = MRBook()
    
    expected_position = 0
    for trade in trades:
        book.add_trade(trade)
        
        if trade.direction == 'long':
            expected_position += trade.quantity
        else:
            expected_position -= trade.quantity
    
    # Property: Book position must equal sum of all trades
    assert book.position == expected_position, (
        f"MRBook position {book.position} does not match expected {expected_position}"
    )


# Additional property test: TrendBook average price is always non-negative
@given(
    positions=st.lists(
        st.tuples(
            st.integers(min_value=-50, max_value=50).filter(lambda x: x != 0),
            st.floats(min_value=10000.0, max_value=30000.0)
        ),
        min_size=1,
        max_size=10
    )
)
@settings(max_examples=100)
def test_property_trend_book_avg_price_non_negative(positions):
    """
    Property: TrendBook Average Price Non-Negative
    
    For any sequence of position additions, the average entry price should 
    always be non-negative (zero only when position is zero).
    """
    book = TrendBook()
    
    for quantity, price in positions:
        try:
            book.add_position(quantity, price)
            
            # Property: Average price must be non-negative
            assert book.avg_entry_price >= 0, (
                f"Average entry price {book.avg_entry_price} is negative"
            )
            
            # Property: If position is non-zero, avg price must be positive
            if book.position != 0:
                assert book.avg_entry_price > 0, (
                    f"Average entry price {book.avg_entry_price} should be positive "
                    f"when position {book.position} is non-zero"
                )
            
        except ValueError:
            # Some combinations might be invalid (e.g., reducing more than available)
            pass


# Additional property test: Unrealized P&L sign consistency
@given(
    position=st.integers(min_value=-100, max_value=100).filter(lambda x: x != 0),
    entry_price=st.floats(min_value=10000.0, max_value=30000.0),
    current_price=st.floats(min_value=10000.0, max_value=30000.0)
)
@settings(max_examples=100)
def test_property_unrealized_pnl_sign_consistency(position, entry_price, current_price):
    """
    Property: Unrealized P&L Sign Consistency
    
    For any position, if price moves in favor of the position, P&L should be positive.
    If price moves against the position, P&L should be negative.
    """
    book = TrendBook()
    book.position = position
    book.avg_entry_price = entry_price
    
    pnl = book.get_unrealized_pnl(current_price)
    
    # Property: P&L sign should match price movement direction
    if position > 0:  # Long position
        if current_price > entry_price:
            assert pnl > 0, f"Long position should have positive P&L when price rises"
        elif current_price < entry_price:
            assert pnl < 0, f"Long position should have negative P&L when price falls"
        else:
            assert pnl == 0, f"P&L should be zero when price unchanged"
    else:  # Short position
        if current_price < entry_price:
            assert pnl > 0, f"Short position should have positive P&L when price falls"
        elif current_price > entry_price:
            assert pnl < 0, f"Short position should have negative P&L when price rises"
        else:
            assert pnl == 0, f"P&L should be zero when price unchanged"


# Additional property test: MR entry requires trend position
@given(
    trend_position=st.integers(min_value=-100, max_value=100),
    mr_quantity=st.integers(min_value=1, max_value=50)
)
@settings(max_examples=100)
def test_property_mr_entry_requires_trend_position(trend_position, mr_quantity):
    """
    Property: MR Entry Requires Trend Position
    
    For any MR entry signal, if trend position is zero, the entry must be rejected.
    """
    pm = PositionManager()
    pm.trend_book.position = trend_position
    
    signal = Signal(
        signal_type=SignalType.ENTRY_SHORT,
        engine='mr',
        quantity=mr_quantity,
        reason='Test',
        timestamp=datetime.now(),
        price=18000.0
    )
    
    can_enter = pm.can_enter_mr_position(signal)
    
    # Property: If trend position is zero, MR entry must be rejected
    if trend_position == 0:
        assert can_enter is False, (
            f"MR entry should be rejected when trend position is zero"
        )
