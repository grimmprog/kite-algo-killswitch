"""
Verification script for OrderExecutor implementation.

This script tests:
1. Kite connection establishment
2. OrderExecutor initialization
3. Broker position query
4. Trade ledger functionality
"""

import sys
import os
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from hybrid_trading.execution import OrderExecutor, ExecutionConfig, Signal
from hybrid_trading.execution.kite_integration import get_kite_connection, test_connection
from hybrid_trading.common.enums import SignalType


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def verify_kite_connection():
    """Verify Kite connection establishment."""
    print("\n" + "="*60)
    print("TEST 1: Kite Connection")
    print("="*60)
    
    try:
        success = test_connection()
        if success:
            print("✓ Kite connection verified")
            return True
        else:
            print("✗ Kite connection failed")
            return False
    except Exception as e:
        print(f"✗ Connection test error: {e}")
        return False


def verify_order_executor_init():
    """Verify OrderExecutor initialization."""
    print("\n" + "="*60)
    print("TEST 2: OrderExecutor Initialization")
    print("="*60)
    
    try:
        # Get Kite connection
        kite = get_kite_connection()
        
        # Create config
        config = ExecutionConfig(
            symbol='NIFTY24JANFUT',
            exchange='NFO',
            order_timeout=10,
            use_limit_orders=False,
            max_retry_attempts=3
        )
        
        # Create OrderExecutor
        executor = OrderExecutor(kite, config)
        
        print(f"✓ OrderExecutor initialized")
        print(f"  - Symbol: {config.symbol}")
        print(f"  - Exchange: {config.exchange}")
        print(f"  - Order timeout: {config.order_timeout}s")
        print(f"  - Max retries: {config.max_retry_attempts}")
        
        return executor
        
    except Exception as e:
        print(f"✗ OrderExecutor initialization failed: {e}")
        return None


def verify_broker_position_query(executor: OrderExecutor):
    """Verify broker position query."""
    print("\n" + "="*60)
    print("TEST 3: Broker Position Query")
    print("="*60)
    
    try:
        # Query position
        position = executor.get_broker_position()
        
        print(f"✓ Broker position query successful")
        print(f"  - Current position: {position}")
        
        return True
        
    except Exception as e:
        print(f"✗ Broker position query failed: {e}")
        return False


def verify_order_type_selection(executor: OrderExecutor):
    """Verify order type selection logic."""
    print("\n" + "="*60)
    print("TEST 4: Order Type Selection")
    print("="*60)
    
    try:
        # Test entry signal (should use LIMIT if configured, else MARKET)
        entry_signal = Signal(
            signal_type=SignalType.ENTRY_LONG,
            engine='trend',
            quantity=50,
            reason='Test entry',
            timestamp=datetime.now(),
            price=19500.0
        )
        
        order_type_entry = executor._select_order_type(entry_signal)
        print(f"✓ Entry signal order type: {order_type_entry}")
        
        # Test exit signal (should always use MARKET)
        exit_signal = Signal(
            signal_type=SignalType.EXIT_FULL,
            engine='trend',
            quantity=50,
            reason='Test exit',
            timestamp=datetime.now(),
            price=19550.0
        )
        
        order_type_exit = executor._select_order_type(exit_signal)
        print(f"✓ Exit signal order type: {order_type_exit}")
        
        # Verify exit is always MARKET
        if order_type_exit != 'MARKET':
            print(f"✗ Exit should use MARKET, got {order_type_exit}")
            return False
        
        print("✓ Order type selection logic verified")
        return True
        
    except Exception as e:
        print(f"✗ Order type selection test failed: {e}")
        return False


def verify_trade_ledger(executor: OrderExecutor):
    """Verify trade ledger functionality."""
    print("\n" + "="*60)
    print("TEST 5: Trade Ledger")
    print("="*60)
    
    try:
        # Get ledger
        ledger = executor.get_trade_ledger()
        print(f"✓ Trade ledger retrieved: {len(ledger)} entries")
        
        # Get summary
        summary = executor.get_ledger_summary()
        print(f"✓ Ledger summary:")
        print(f"  - Total orders: {summary['total_orders']}")
        print(f"  - Completed: {summary['completed']}")
        print(f"  - Rejected: {summary['rejected']}")
        print(f"  - Pending: {summary['pending']}")
        print(f"  - Trend orders: {summary['trend_orders']}")
        print(f"  - MR orders: {summary['mr_orders']}")
        print(f"  - Success rate: {summary['success_rate']:.1f}%")
        
        return True
        
    except Exception as e:
        print(f"✗ Trade ledger test failed: {e}")
        return False


def main():
    """Run all verification tests."""
    print("\n" + "="*60)
    print("OrderExecutor Verification")
    print("="*60)
    
    results = []
    
    # Test 1: Kite connection
    results.append(("Kite Connection", verify_kite_connection()))
    
    # Test 2: OrderExecutor initialization
    executor = verify_order_executor_init()
    results.append(("OrderExecutor Init", executor is not None))
    
    if executor is None:
        print("\n✗ Cannot proceed without OrderExecutor")
        return
    
    # Test 3: Broker position query
    results.append(("Broker Position Query", verify_broker_position_query(executor)))
    
    # Test 4: Order type selection
    results.append(("Order Type Selection", verify_order_type_selection(executor)))
    
    # Test 5: Trade ledger
    results.append(("Trade Ledger", verify_trade_ledger(executor)))
    
    # Summary
    print("\n" + "="*60)
    print("VERIFICATION SUMMARY")
    print("="*60)
    
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All verification tests passed!")
    else:
        print(f"\n✗ {total - passed} test(s) failed")


if __name__ == '__main__':
    main()
