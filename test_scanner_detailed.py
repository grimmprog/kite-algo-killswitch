#!/usr/bin/env python3
"""
Detailed Scanner Test - Shows exactly why signals are rejected
"""
import sys
import logging
import pandas as pd
from scanner import market_scanner
from strategy import strategy_engine
import config

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_scanner_with_details():
    """Test scanner and show detailed rejection reasons"""
    print("=" * 70)
    print("DETAILED SCANNER TEST")
    print("=" * 70)
    print()
    
    print(f"Watchlist: {config.WATCHLIST}")
    print(f"Confidence Threshold: {config.CONFIDENCE_THRESHOLD}%")
    print()
    
    for symbol in config.WATCHLIST:
        print("=" * 70)
        print(f"ANALYZING: {symbol}")
        print("=" * 70)
        
        # Fetch data
        print("\n1️⃣ Fetching market data...")
        df = market_scanner.fetch_ohlc(symbol)
        
        if df.empty:
            print(f"❌ No data available for {symbol}")
            print()
            continue
        
        print(f"✅ Got {len(df)} data points")
        print(f"   Latest Close: ₹{df.iloc[-1]['close']:.2f}")
        print(f"   Date Range: {df.iloc[0]['date']} to {df.iloc[-1]['date']}")
        
        # Prepare data with indicators
        print("\n2️⃣ Calculating indicators...")
        df = strategy_engine.prepare_data(df)
        
        if len(df) < 5:
            print(f"❌ Insufficient data for analysis ({len(df)} rows)")
            continue
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        print(f"✅ Indicators calculated")
        print(f"   Close: ₹{last['close']:.2f}")
        print(f"   VWAP: ₹{last['vwap']:.2f}")
        print(f"   EMA 20: ₹{last['ema_20']:.2f}")
        print(f"   MACD: {last['macd']:.4f}")
        print(f"   Volume: {last['volume']:,.0f}")
        
        # Check each condition
        print("\n3️⃣ Checking strategy conditions...")
        print()
        
        # Market Time
        print("   📅 Market Time Check:")
        ok, msg = strategy_engine.check_market_time()
        if ok:
            print(f"      ✅ {msg}")
        else:
            print(f"      ❌ {msg}")
            print()
            continue
        
        # Trend
        print("\n   📉 Bearish Trend Check:")
        ok, msg = strategy_engine.check_trend_bearish(df)
        if ok:
            print(f"      ✅ {msg}")
            print(f"         - Price < VWAP: {last['close']:.2f} < {last['vwap']:.2f}")
            print(f"         - EMA Sloping Down: {last['ema_20']:.2f} < {prev['ema_20']:.2f}")
            print(f"         - MACD < 0: {last['macd']:.4f}")
        else:
            print(f"      ❌ {msg}")
            print(f"         - Price vs VWAP: {last['close']:.2f} vs {last['vwap']:.2f}")
            print(f"         - EMA Trend: {last['ema_20']:.2f} vs {prev['ema_20']:.2f}")
            print(f"         - MACD: {last['macd']:.4f}")
        
        # Impulse
        print("\n   ⚡ Impulse Check:")
        ok, msg = strategy_engine.check_impulse(df)
        if ok:
            print(f"      ✅ {msg}")
        else:
            print(f"      ❌ {msg}")
            avg_body = df['body_size'].rolling(20).mean().iloc[-1]
            print(f"         - Avg Body Size: {avg_body:.2f}")
            print(f"         - Recent Max Volume: {df['volume'].iloc[-10:].max():,.0f}")
        
        # Entry Trigger
        print("\n   🎯 Entry Trigger Check:")
        ok, msg = strategy_engine.check_entry_trigger(df)
        if ok:
            print(f"      ✅ {msg}")
        else:
            print(f"      ❌ {msg}")
            print(f"         - Current Close: {last['close']:.2f}")
            print(f"         - Previous Low: {prev['low']:.2f}")
            print(f"         - Current Color: {last['color']}")
            print(f"         - Volume: {last['volume']:,.0f} vs {prev['volume']:,.0f}")
        
        # Confidence
        print("\n   🎲 Confidence Score:")
        confidence = strategy_engine.calculate_confidence(df)
        threshold = config.CONFIDENCE_THRESHOLD
        if confidence >= threshold:
            print(f"      ✅ {confidence}% (threshold: {threshold}%)")
        else:
            print(f"      ❌ {confidence}% (threshold: {threshold}%)")
        
        # Final Signal
        print("\n4️⃣ Final Signal:")
        signal, msg = strategy_engine.get_signal(df)
        if signal:
            print(f"   ✅ SIGNAL GENERATED: {msg}")
            print(f"      Type: {signal['type']}")
            print(f"      Stop Loss: ₹{signal['stop_loss']:.2f}")
            print(f"      Confidence: {signal['confidence']}%")
        else:
            print(f"   ❌ NO SIGNAL: {msg}")
        
        print()
    
    print("=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    try:
        test_scanner_with_details()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)
