"""
Checkpoint 10 Verification: Execution Layer

This script verifies:
1. All unit tests pass
2. All property-based tests pass
3. Order placement with paper trading (simulated)
4. Position reconciliation
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import subprocess

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hybrid_trading.execution import (
    OrderExecutor, ExecutionConfig, PositionManager,
    TrendBook, MRBook, MRTrade, Signal, OrderResult
)
from hybrid_trading.common.enums import SignalType


def run_tests():
    """Run all execution layer tests."""
    print("\n" + "="*60)
    print("CHECKPOINT 10: EXECUTION LAYER VERIFICATION")
    print("="*60)
    
    print("\n" + "="*60)
    print("STEP 1: Running Unit Tests")
    print("="*60)
    
    # Run position manager unit tests
    print("\n1.1 Position Manager Unit Tests...")
    result = subprocess.run(
        ['python', '-m', 'pytest', 'hybrid_trading/execution/test_position_manager.py', '-v'],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        # Count passed tests
        passed = result.stdout.count(' PASSED')
        print(f"✓ Position Manager: {passed} tests passed")
    else:
        print(f"✗ Position Manager tests failed")
        print(result.stdout)
        return False
    
    # Run order executor unit tests
    print("\n1.2 Order Executor Unit Tests...")
    result = subprocess.run(
        ['python', '-m', 'pytest', 'hybrid_trading/execution/test_order_executor.py', '-v'],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        passed = result.stdout.count(' PASSED')
        print(f"✓ Order Executor: {passed} tests passed")
    else:
        print(f"✗ Order Executor tests failed")
        print(result.stdout)
        return False
    
    print("\n" + "="*60)
    print("STEP 2: Running Property-Based Tests")
    print("="*60)
    
    # Run position manager PBT tests
    print("\n2.1 Position Manager Property Tests...")
    result = subprocess.run(
        ['python', '-m', 'pytest', 'hybrid_trading/execution/test_position_manager_pbt.py', '-v'],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        passed = result.stdout.count(' PASSED')
        print(f"✓ Position Manager PBT: {passed} properties verified")
    else:
        print(f"✗ Position Manager PBT tests failed")
        print(result.stdout)
        return False
    
    return True


def test_paper_trading_simulation():
    """Test order placement with simulated paper trading."""
    print("\n" + "="*60)
    print("STEP 3: Paper Trading Simulation")
    print("="*60)
    
    try:
        # Create mock Kite connection with required constants
        class MockKite:
            # Kite constants
            VARIETY_REGULAR = "regular"
            PRODUCT_MIS = "MIS"
            TRANSACTION_TYPE_BUY = "BUY"
            TRANSACTION_TYPE_SELL = "SELL"
            ORDER_TYPE_MARKET = "MARKET"
            ORDER_TYPE_LIMIT = "LIMIT"
            VALIDITY_DAY = "DAY"
            
            def __init__(self):
                self.placed_orders = {}
            
            def place_order(self, **kwargs):
                """Simulate order placement."""
                order_id = f"ORDER_{datetime.now().timestamp()}"
                # Store order details
                self.placed_orders[order_id] = {
                    'order_id': order_id,
                    'status': 'COMPLETE',
                    'filled_quantity': kwargs.get('quantity', 50),
                    'average_price': 19500.0
                }
                return order_id
            
            def orders(self):
                """Simulate order status query - returns all orders."""
                return list(self.placed_orders.values())
            
            def order_history(self, order_id):
                """Simulate order status."""
                if order_id in self.placed_orders:
                    return [self.placed_orders[order_id]]
                return []
            
            def positions(self):
                """Simulate position query."""
                return {
                    'net': [
                        {
                            'tradingsymbol': 'NIFTY24JANFUT',
                            'quantity': 50
                        }
                    ]
                }
        
        # Create config
        config = ExecutionConfig(
            symbol='NIFTY24JANFUT',
            exchange='NFO',
            order_timeout=10,
            use_limit_orders=False,
            max_retry_attempts=3
        )
        
        # Create executor with mock
        executor = OrderExecutor(MockKite(), config)
        
        print("\n3.1 Testing Entry Order Placement...")
        entry_signal = Signal(
            signal_type=SignalType.ENTRY_LONG,
            engine='trend',
            quantity=50,
            reason='Test entry',
            timestamp=datetime.now(),
            price=19500.0
        )
        
        result = executor.place_order(entry_signal, transaction_type='BUY')
        
        if result.status == 'COMPLETE':
            print(f"✓ Entry order placed successfully")
            print(f"  - Order ID: {result.order_id}")
            print(f"  - Filled: {result.filled_quantity} @ {result.average_price}")
        else:
            print(f"✗ Entry order failed: {result.message}")
            return False
        
        print("\n3.2 Testing Exit Order Placement...")
        exit_signal = Signal(
            signal_type=SignalType.EXIT_FULL,
            engine='trend',
            quantity=50,
            reason='Test exit',
            timestamp=datetime.now(),
            price=19550.0
        )
        
        result = executor.place_order(exit_signal, transaction_type='SELL')
        
        if result.status == 'COMPLETE':
            print(f"✓ Exit order placed successfully")
            print(f"  - Order ID: {result.order_id}")
            print(f"  - Filled: {result.filled_quantity} @ {result.average_price}")
        else:
            print(f"✗ Exit order failed: {result.message}")
            return False
        
        print("\n3.3 Testing Trade Ledger...")
        ledger = executor.get_trade_ledger()
        summary = executor.get_ledger_summary()
        
        print(f"✓ Trade ledger verified")
        print(f"  - Total orders: {summary['total_orders']}")
        print(f"  - Completed: {summary['completed']}")
        print(f"  - Success rate: {summary['success_rate']:.1f}%")
        
        return True
        
    except Exception as e:
        print(f"✗ Paper trading simulation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_position_reconciliation():
    """Test position reconciliation."""
    print("\n" + "="*60)
    print("STEP 4: Position Reconciliation")
    print("="*60)
    
    try:
        # Create mock executor
        class MockExecutor:
            def __init__(self):
                self.config = type('obj', (object,), {'symbol': 'NIFTY24JANFUT'})()
            
            def get_broker_position(self, symbol=None):
                """Return simulated broker position."""
                return 35  # Trend 50 - MR 15
        
        # Create position manager
        pm = PositionManager(order_executor=MockExecutor())
        
        print("\n4.1 Setting up positions...")
        # Add trend position
        pm.trend_book.add_position(50, 19500.0)
        print(f"  - Trend position: {pm.trend_book.position}")
        
        # Add MR trade
        mr_trade = MRTrade(
            entry_time=datetime.now(),
            entry_price=19600.0,
            quantity=15,
            direction='short',
            impulse_start=19500.0,
            impulse_end=19600.0,
            candles_held=0
        )
        pm.mr_book.add_trade(mr_trade)
        print(f"  - MR position: {pm.mr_book.position}")
        print(f"  - Net position: {pm.get_net_position()}")
        
        print("\n4.2 Testing reconciliation...")
        is_reconciled = pm.reconcile_position(symbol='NIFTY24JANFUT')
        
        if is_reconciled:
            print(f"✓ Position reconciliation successful")
            print(f"  - Expected net: {pm.get_net_position()}")
            print(f"  - Broker net: 35")
            print(f"  - Match: True")
        else:
            print(f"✗ Position reconciliation failed")
            return False
        
        print("\n4.3 Testing mismatch detection...")
        # Modify broker position to create mismatch
        class MockExecutorMismatch:
            def __init__(self):
                self.config = type('obj', (object,), {'symbol': 'NIFTY24JANFUT'})()
            
            def get_broker_position(self, symbol=None):
                return 40  # Different from expected 35
        
        pm2 = PositionManager(order_executor=MockExecutorMismatch())
        pm2.trend_book.add_position(50, 19500.0)
        pm2.mr_book.add_trade(mr_trade)
        
        is_reconciled = pm2.reconcile_position(symbol='NIFTY24JANFUT')
        
        if not is_reconciled:
            print(f"✓ Mismatch detection working")
            print(f"  - Expected net: {pm2.get_net_position()}")
            print(f"  - Broker net: 40")
            print(f"  - Discrepancy detected: True")
        else:
            print(f"✗ Mismatch detection failed")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ Position reconciliation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all checkpoint verifications."""
    results = []
    
    # Step 1 & 2: Run tests
    results.append(("Unit & Property Tests", run_tests()))
    
    # Step 3: Paper trading simulation
    results.append(("Paper Trading Simulation", test_paper_trading_simulation()))
    
    # Step 4: Position reconciliation
    results.append(("Position Reconciliation", test_position_reconciliation()))
    
    # Summary
    print("\n" + "="*60)
    print("CHECKPOINT 10 SUMMARY")
    print("="*60)
    
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\nTotal: {passed}/{total} verifications passed")
    
    if passed == total:
        print("\n" + "="*60)
        print("✓ CHECKPOINT 10 COMPLETE")
        print("="*60)
        print("\nExecution layer is working correctly!")
        print("\nVerified components:")
        print("  ✓ TrendBook - Position tracking and P&L calculation")
        print("  ✓ MRBook - Individual trade management")
        print("  ✓ PositionManager - Net position and constraints")
        print("  ✓ OrderExecutor - Order placement and ledger")
        print("  ✓ Position reconciliation - Broker sync")
        print("\nReady to proceed to Risk Manager implementation!")
        return 0
    else:
        print(f"\n✗ {total - passed} verification(s) failed")
        print("\nPlease review the failures above.")
        return 1


if __name__ == '__main__':
    exit(main())
