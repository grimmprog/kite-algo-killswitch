#!/usr/bin/env python3
"""
Debug script to check what Kite API is returning for positions
"""
from connect import get_kite_session
import json

def debug_positions():
    """Fetch and display raw position data from Kite"""
    print("=" * 70)
    print("DEBUG: Kite Positions Data")
    print("=" * 70)
    print()
    
    try:
        kite = get_kite_session()
        
        # Get positions
        positions_data = kite.positions()
        
        print("Raw Positions Response:")
        print(json.dumps(positions_data, indent=2, default=str))
        print()
        
        # Check net positions
        net_positions = positions_data.get('net', [])
        print(f"\nNet Positions Count: {len(net_positions)}")
        print()
        
        # Show each position in detail
        for i, pos in enumerate(net_positions, 1):
            if pos['quantity'] != 0:
                print(f"Position #{i}:")
                print(f"  Trading Symbol: {pos['tradingsymbol']}")
                print(f"  Quantity: {pos['quantity']}")
                print(f"  Average Price: ₹{pos['average_price']:.2f}")
                print(f"  Last Price: ₹{pos['last_price']:.2f}")
                print(f"  P&L: ₹{pos['pnl']:.2f}")
                print(f"  Day P&L: ₹{pos.get('day_pnl', 0):.2f}")
                print(f"  Unrealised P&L: ₹{pos.get('unrealised', 0):.2f}")
                print(f"  Realised P&L: ₹{pos.get('realised', 0):.2f}")
                print(f"  Value: ₹{pos.get('value', 0):.2f}")
                print(f"  Buy Quantity: {pos.get('buy_quantity', 0)}")
                print(f"  Sell Quantity: {pos.get('sell_quantity', 0)}")
                print(f"  Buy Price: ₹{pos.get('buy_price', 0):.2f}")
                print(f"  Sell Price: ₹{pos.get('sell_price', 0):.2f}")
                print(f"  Buy Value: ₹{pos.get('buy_value', 0):.2f}")
                print(f"  Sell Value: ₹{pos.get('sell_value', 0):.2f}")
                print()
                
                # Manual P&L calculation
                manual_pnl = (pos['last_price'] - pos['average_price']) * pos['quantity']
                print(f"  Manual P&L Calculation:")
                print(f"    (LTP - Avg) × Qty = ({pos['last_price']:.2f} - {pos['average_price']:.2f}) × {pos['quantity']}")
                print(f"    = ₹{manual_pnl:.2f}")
                print()
                
                if abs(manual_pnl - pos['pnl']) > 0.01:
                    print(f"  ⚠️  MISMATCH! Kite P&L: ₹{pos['pnl']:.2f}, Manual: ₹{manual_pnl:.2f}")
                    print(f"  Difference: ₹{abs(manual_pnl - pos['pnl']):.2f}")
                else:
                    print(f"  ✅ P&L matches manual calculation")
                print()
                print("-" * 70)
                print()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_positions()
