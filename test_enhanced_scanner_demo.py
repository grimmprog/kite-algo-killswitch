#!/usr/bin/env python3
"""
Demo Enhanced Scanner - Simulates trading hours to show functionality
"""
import sys
import logging
import datetime
from enhanced_scanner import enhanced_scanner
import config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def main():
    print("\n" + "=" * 70)
    print("ENHANCED SCANNER DEMO")
    print("Scanning for BULLISH (CE) and BEARISH (PE) setups")
    print("=" * 70)
    print()
    
    print(f"Current Time: {datetime.datetime.now().strftime('%H:%M:%S IST')}")
    print(f"Trading Window: {config.START_TIME} - {config.END_TIME}")
    print("⚠️  Simulating trading hours for demo...")
    print()
    
    # Temporarily override time check
    original_start = config.START_TIME
    original_end = config.END_TIME
    
    # Set to always pass time check
    config.START_TIME = datetime.time(0, 0)
    config.END_TIME = datetime.time(23, 59)
    
    try:
        # Run scanner
        signals = enhanced_scanner.scan()
        
        # Display results
        print("\n" + "=" * 70)
        print("SCAN RESULTS")
        print("=" * 70)
        
        if not signals:
            print("\n❌ No trading signals found")
            print("   Market conditions not favorable for entry")
            print()
            print("📊 This means:")
            print("   - No clear bullish trend for CE (Call) options")
            print("   - No clear bearish trend for PE (Put) options")
            print("   - Market is in consolidation or mixed signals")
        else:
            print(f"\n✅ Found {len(signals)} signal(s):\n")
            
            for i, signal in enumerate(signals, 1):
                direction_emoji = "📈" if signal['direction'] == 'BULLISH' else "📉"
                print(f"{direction_emoji} Signal #{i}: {signal['index']} ({signal['exchange']})")
                print(f"   Direction: {signal['direction']}")
                print(f"   Option Type: {signal['option_type']}")
                print(f"   Spot Price: ₹{signal['spot_price']:.2f}")
                print(f"   ")
                print(f"   Recommended Strikes:")
                print(f"   ├─ ATM: {signal['strikes']['ATM']} (At The Money)")
                print(f"   └─ ITM: {signal['strikes']['ITM']} (In The Money)")
                print(f"   ")
                print(f"   Confidence: {signal['confidence']}%")
                print(f"   Stop Loss: ₹{signal['stop_loss']:.2f}")
                print(f"   Target: ₹{signal['target']:.2f}")
                print(f"   Reason: {signal['reason']}")
                print()
        
        print("=" * 70)
        print()
        print("📝 How to use these signals:")
        print("   1. Check the direction (BULLISH = Buy CE, BEARISH = Buy PE)")
        print("   2. Use ATM strike for balanced risk/reward")
        print("   3. Use ITM strike for higher probability, lower returns")
        print("   4. Set stop loss at the given level")
        print("   5. Book profits at target or trail stop loss")
        print()
        
    finally:
        # Restore original times
        config.START_TIME = original_start
        config.END_TIME = original_end

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted")
    except Exception as e:
        logging.error(f"Demo failed: {e}", exc_info=True)
        sys.exit(1)
