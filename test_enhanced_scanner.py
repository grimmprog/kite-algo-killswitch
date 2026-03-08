#!/usr/bin/env python3
"""
Test Enhanced Scanner - Shows both CE and PE signals with ATM/ITM strikes
"""
import sys
import logging
from enhanced_scanner import enhanced_scanner

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def main():
    print("\n" + "=" * 70)
    print("ENHANCED SCANNER TEST")
    print("Scanning for BULLISH (CE) and BEARISH (PE) setups")
    print("=" * 70)
    print()
    
    # Run scanner
    signals = enhanced_scanner.scan()
    
    # Display results
    print("\n" + "=" * 70)
    print("SCAN RESULTS")
    print("=" * 70)
    
    if not signals:
        print("\n❌ No trading signals found")
        print("   Market conditions not favorable for entry")
    else:
        print(f"\n✅ Found {len(signals)} signal(s):\n")
        
        for i, signal in enumerate(signals, 1):
            print(f"{i}. {signal['index']} ({signal['exchange']}) - {signal['direction']}")
            print(f"   Option Type: {signal['option_type']}")
            print(f"   Spot Price: ₹{signal['spot_price']:.2f}")
            print(f"   ATM Strike: {signal['strikes']['ATM']}")
            print(f"   ITM Strike: {signal['strikes']['ITM']}")
            print(f"   Confidence: {signal['confidence']}%")
            print(f"   Stop Loss: ₹{signal['stop_loss']:.2f}")
            print(f"   Target: ₹{signal['target']:.2f}")
            print(f"   Reason: {signal['reason']}")
            print()
    
    print("=" * 70)
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted")
    except Exception as e:
        logging.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)
