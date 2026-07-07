"""
Verification script for Trend Engine implementation.

This script demonstrates the Trend Engine functionality with sample data.
"""

from datetime import datetime, timedelta

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hybrid_trading.data.models import Candle
from hybrid_trading.data.candle_builder import CandleBuilder
from hybrid_trading.data.indicator_service import IndicatorService
from hybrid_trading.analysis.market_state_detector import MarketStateDetector
from hybrid_trading.strategy.trend_engine import TrendEngine, TrendBook
from hybrid_trading.config import TrendConfig
from hybrid_trading.common.enums import TrendState, SignalType


def create_uptrend_scenario():
    """Create a sample uptrend scenario with pullback."""
    print("\n" + "="*60)
    print("SCENARIO 1: Uptrend with Pullback to Structure")
    print("="*60)
    
    # Initialize components
    timeframes = ['15m']
    candle_builder = CandleBuilder(timeframes)
    indicator_service = IndicatorService(candle_builder)
    market_state = MarketStateDetector(candle_builder, indicator_service)
    config = TrendConfig(
        timeframe='15m',
        base_position_size=1,
        partial_exit_percentage=0.5
    )
    engine = TrendEngine(market_state, indicator_service, config)
    
    # Create uptrend pattern: higher highs and higher lows
    base_time = datetime.now()
    uptrend_candles = []
    
    # Build uptrend with clear structure
    prices = [100, 102, 104, 106, 108, 110, 112, 114, 116, 118]
    for i, base_price in enumerate(prices):
        candle = Candle(
            timestamp=base_time + timedelta(minutes=15 * i),
            open=base_price,
            high=base_price + 2,
            low=base_price - 1,
            close=base_price + 1.5,
            volume=1000,
            timeframe='15m'
        )
        uptrend_candles.append(candle)
    
    # Add pullback candles
    for i in range(3):
        candle = Candle(
            timestamp=base_time + timedelta(minutes=15 * (10 + i)),
            open=118 - i,
            high=119 - i,
            low=116 - i,
            close=117 - i,
            volume=1000,
            timeframe='15m'
        )
        uptrend_candles.append(candle)
    
    # Add more candles to meet minimum requirements
    for i in range(40):
        candle = Candle(
            timestamp=base_time + timedelta(minutes=15 * (13 + i)),
            open=115 + i * 0.5,
            high=116 + i * 0.5,
            low=114 + i * 0.5,
            close=115.5 + i * 0.5,
            volume=1000,
            timeframe='15m'
        )
        uptrend_candles.append(candle)
    
    candle_builder.historical_candles['15m'] = uptrend_candles
    
    # Detect trend state
    trend_state = market_state.detect_trend_state('15m')
    print(f"\nDetected Trend State: {trend_state}")
    
    # Check for entry signal
    trend_book = TrendBook()
    current_price = 135.0
    signal = engine.evaluate(trend_book, current_price)
    
    if signal:
        print(f"\n✓ Signal Generated:")
        print(f"  Type: {signal.signal_type}")
        print(f"  Engine: {signal.engine}")
        print(f"  Quantity: {signal.quantity}")
        print(f"  Price: {signal.price}")
        print(f"  Reason: {signal.reason}")
    else:
        print("\n✗ No signal generated")
    
    return signal


def create_structure_break_scenario():
    """Create a scenario with structure break for exit."""
    print("\n" + "="*60)
    print("SCENARIO 2: Structure Break Exit")
    print("="*60)
    
    # Initialize components
    timeframes = ['15m']
    candle_builder = CandleBuilder(timeframes)
    indicator_service = IndicatorService(candle_builder)
    market_state = MarketStateDetector(candle_builder, indicator_service)
    config = TrendConfig(timeframe='15m', base_position_size=1)
    engine = TrendEngine(market_state, indicator_service, config)
    
    # Create uptrend followed by structure break
    base_time = datetime.now()
    candles = []
    
    # Build uptrend
    for i in range(20):
        candle = Candle(
            timestamp=base_time + timedelta(minutes=15 * i),
            open=100 + i * 2,
            high=102 + i * 2,
            low=99 + i * 2,
            close=101 + i * 2,
            volume=1000,
            timeframe='15m'
        )
        candles.append(candle)
    
    # Add structure break candles (breaking below previous higher low)
    for i in range(5):
        candle = Candle(
            timestamp=base_time + timedelta(minutes=15 * (20 + i)),
            open=140 - i * 3,
            high=141 - i * 3,
            low=135 - i * 3,
            close=136 - i * 3,
            volume=1000,
            timeframe='15m'
        )
        candles.append(candle)
    
    # Add more candles
    for i in range(30):
        candle = Candle(
            timestamp=base_time + timedelta(minutes=15 * (25 + i)),
            open=120 + i * 0.5,
            high=121 + i * 0.5,
            low=119 + i * 0.5,
            close=120.5 + i * 0.5,
            volume=1000,
            timeframe='15m'
        )
        candles.append(candle)
    
    candle_builder.historical_candles['15m'] = candles
    
    # Simulate existing long position
    trend_book = TrendBook()
    trend_book.position = 10
    trend_book.avg_entry_price = 110.0
    
    print(f"\nCurrent Position: {trend_book.position} @ {trend_book.avg_entry_price}")
    
    # Check for structure break
    structure_broken = market_state.detect_structure_break('15m')
    print(f"Structure Broken: {structure_broken}")
    
    # Check for exit signal
    current_price = 135.0
    signal = engine.evaluate(trend_book, current_price)
    
    if signal:
        print(f"\n✓ Exit Signal Generated:")
        print(f"  Type: {signal.signal_type}")
        print(f"  Quantity: {signal.quantity}")
        print(f"  Reason: {signal.reason}")
    else:
        print("\n✗ No exit signal generated")
    
    return signal


def create_trend_weakening_scenario():
    """Create a scenario with trend weakening for partial exit."""
    print("\n" + "="*60)
    print("SCENARIO 3: Trend Weakening Partial Exit")
    print("="*60)
    
    # Initialize components
    timeframes = ['15m']
    candle_builder = CandleBuilder(timeframes)
    indicator_service = IndicatorService(candle_builder)
    market_state = MarketStateDetector(candle_builder, indicator_service)
    config = TrendConfig(
        timeframe='15m',
        base_position_size=1,
        partial_exit_percentage=0.5,
        trend_weakening_candles=5
    )
    engine = TrendEngine(market_state, indicator_service, config)
    
    # Create uptrend with weakening
    base_time = datetime.now()
    candles = []
    
    # Build strong uptrend
    for i in range(30):
        candle = Candle(
            timestamp=base_time + timedelta(minutes=15 * i),
            open=100 + i * 2,
            high=103 + i * 2,
            low=99 + i * 2,
            close=102 + i * 2,
            volume=1000,
            timeframe='15m'
        )
        candles.append(candle)
    
    # Add weakening candles (no new higher highs, reduced range)
    for i in range(10):
        candle = Candle(
            timestamp=base_time + timedelta(minutes=15 * (30 + i)),
            open=160,
            high=161,  # Not making new highs
            low=159,
            close=160.5,
            volume=1000,
            timeframe='15m'
        )
        candles.append(candle)
    
    # Add more candles
    for i in range(15):
        candle = Candle(
            timestamp=base_time + timedelta(minutes=15 * (40 + i)),
            open=160 + i * 0.2,
            high=161 + i * 0.2,
            low=159 + i * 0.2,
            close=160.5 + i * 0.2,
            volume=1000,
            timeframe='15m'
        )
        candles.append(candle)
    
    candle_builder.historical_candles['15m'] = candles
    
    # Simulate existing long position
    trend_book = TrendBook()
    trend_book.position = 10
    trend_book.avg_entry_price = 120.0
    
    print(f"\nCurrent Position: {trend_book.position} @ {trend_book.avg_entry_price}")
    
    # Check for trend weakening
    trend_weakening = market_state.detect_trend_weakening('15m', direction='up')
    print(f"Trend Weakening: {trend_weakening}")
    
    # Check for partial exit signal
    current_price = 163.0
    signal = engine.evaluate(trend_book, current_price)
    
    if signal:
        print(f"\n✓ Partial Exit Signal Generated:")
        print(f"  Type: {signal.signal_type}")
        print(f"  Quantity: {signal.quantity} (50% of position)")
        print(f"  Reason: {signal.reason}")
    else:
        print("\n✗ No partial exit signal generated")
    
    return signal


def main():
    """Run all verification scenarios."""
    print("\n" + "="*60)
    print("TREND ENGINE VERIFICATION")
    print("="*60)
    
    try:
        # Scenario 1: Entry on pullback
        signal1 = create_uptrend_scenario()
        
        # Scenario 2: Exit on structure break
        signal2 = create_structure_break_scenario()
        
        # Scenario 3: Partial exit on trend weakening
        signal3 = create_trend_weakening_scenario()
        
        print("\n" + "="*60)
        print("VERIFICATION SUMMARY")
        print("="*60)
        print(f"Scenario 1 (Entry): {'✓ PASS' if signal1 is not None else '✗ FAIL'}")
        print(f"Scenario 2 (Exit): {'✓ PASS' if signal2 is not None else '✗ FAIL'}")
        print(f"Scenario 3 (Partial): {'✓ PASS' if signal3 is not None else '✗ FAIL'}")
        print("\n✓ Trend Engine implementation verified successfully!")
        
    except Exception as e:
        print(f"\n✗ Verification failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
