"""
Quick validation test for hybrid trading system setup.
Tests that all core data models and configuration work correctly.
"""

from datetime import datetime
from hybrid_trading.data import Tick, Candle
from hybrid_trading.common import TrendState, MRState, SignalType
from hybrid_trading.execution import Signal, Trade, MRTrade, OrderResult
from hybrid_trading.config import SystemConfig, TrendConfig, MRConfig, RiskConfig, ExecutionConfig


def test_tick_creation():
    """Test Tick model creation and validation."""
    tick = Tick(
        timestamp=datetime.now(),
        symbol='NIFTY FUT',
        last_price=18500.0,
        volume=100
    )
    assert tick.last_price == 18500.0
    assert tick.volume == 100
    print("✓ Tick creation successful")


def test_candle_creation():
    """Test Candle model creation and properties."""
    candle = Candle(
        timestamp=datetime.now(),
        open=18450.0,
        high=18520.0,
        low=18440.0,
        close=18500.0,
        volume=5000,
        timeframe='5m'
    )
    assert candle.body_size == 50.0
    assert candle.range_size == 80.0
    assert candle.is_bullish == True
    assert candle.is_bearish == False
    print("✓ Candle creation and properties successful")


def test_enums():
    """Test enum definitions."""
    assert TrendState.UPTREND.value == "uptrend"
    assert MRState.EXTENDED_UP.value == "extended_up"
    assert SignalType.ENTRY_LONG.is_entry == True
    assert SignalType.EXIT_FULL.is_exit == True
    print("✓ Enums working correctly")


def test_signal_creation():
    """Test Signal model creation."""
    signal = Signal(
        signal_type=SignalType.ENTRY_LONG,
        engine='trend',
        quantity=1,
        reason='Pullback to structure',
        timestamp=datetime.now(),
        price=18500.0
    )
    assert signal.engine == 'trend'
    assert signal.quantity == 1
    print("✓ Signal creation successful")


def test_trade_creation():
    """Test Trade model creation."""
    trade = Trade(
        timestamp=datetime.now(),
        quantity=1,
        price=18500.0,
        trade_type='trend',
        order_id='ORDER123'
    )
    assert trade.is_long == True
    assert trade.is_short == False
    print("✓ Trade creation successful")


def test_mr_trade_creation():
    """Test MRTrade model and retracement calculation."""
    mr_trade = MRTrade(
        entry_time=datetime.now(),
        entry_price=18550.0,
        quantity=1,
        direction='short',
        impulse_start=18450.0,
        impulse_end=18600.0
    )
    
    # Test retracement calculation
    # Impulse: 18450 -> 18600 (150 points)
    # Current: 18520
    # Retracement: 18600 - 18520 = 80 points
    # Percentage: 80/150 * 100 = 53.33%
    retracement = mr_trade.retracement_pct(18520.0)
    assert 53.0 < retracement < 54.0
    print(f"✓ MRTrade creation and retracement calculation successful ({retracement:.1f}%)")


def test_order_result_creation():
    """Test OrderResult model."""
    result = OrderResult(
        order_id='ORDER123',
        status='COMPLETE',
        filled_quantity=1,
        average_price=18500.0,
        message='Order filled successfully'
    )
    assert result.is_complete == True
    assert result.is_rejected == False
    print("✓ OrderResult creation successful")


def test_config_creation():
    """Test configuration creation and validation."""
    config = SystemConfig(
        timeframes=['5m', '15m'],
        instruments=['NIFTY FUT'],
        execution_mode='automated'
    )
    
    # Should not raise any errors
    config.validate()
    
    assert config.trend_config.base_position_size == 1
    assert config.mr_config.max_mr_trades_per_leg == 3
    assert config.risk_config.max_daily_loss_pct == 2.0
    print("✓ Configuration creation and validation successful")


def test_config_to_dict():
    """Test configuration serialization."""
    config = SystemConfig()
    config_dict = config.to_dict()
    
    assert 'timeframes' in config_dict
    assert 'trend_config' in config_dict
    assert 'mr_config' in config_dict
    assert 'risk_config' in config_dict
    assert 'execution_config' in config_dict
    print("✓ Configuration serialization successful")


def test_invalid_configurations():
    """Test that invalid configurations are rejected."""
    try:
        config = SystemConfig(execution_mode='invalid_mode')
        config.validate()
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Invalid execution_mode" in str(e)
        print("✓ Invalid configuration properly rejected")


def main():
    """Run all validation tests."""
    print("\n=== Hybrid Trading System Setup Validation ===\n")
    
    test_tick_creation()
    test_candle_creation()
    test_enums()
    test_signal_creation()
    test_trade_creation()
    test_mr_trade_creation()
    test_order_result_creation()
    test_config_creation()
    test_config_to_dict()
    test_invalid_configurations()
    
    print("\n=== All validation tests passed! ===\n")
    print("Project structure created successfully:")
    print("  ✓ hybrid_trading/data/ - Tick and Candle models")
    print("  ✓ hybrid_trading/analysis/ - Ready for market state detection")
    print("  ✓ hybrid_trading/strategy/ - Ready for trend and MR engines")
    print("  ✓ hybrid_trading/execution/ - Signal, Trade, MRTrade, OrderResult models")
    print("  ✓ hybrid_trading/risk/ - Ready for risk management")
    print("  ✓ hybrid_trading/monitoring/ - Ready for monitoring integration")
    print("  ✓ hybrid_trading/common/ - TrendState, MRState, SignalType enums")
    print("  ✓ hybrid_trading/config.py - SystemConfig with validation")
    print("  ✓ requirements.txt - Updated with hypothesis, pytest, pyyaml")
    print("\nNext: Implement task 2 - Candle Builder and Indicator Service")


if __name__ == '__main__':
    main()
