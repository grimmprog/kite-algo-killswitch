#!/usr/bin/env python3
"""
Test Quote API access after subscription
"""
from connect import get_kite_session
import time

def test_quote_api():
    """Test if quote API works now"""
    print("=" * 70)
    print("TESTING QUOTE API ACCESS")
    print("=" * 70)
    print()
    
    kite = get_kite_session()
    
    # Get current position
    positions = kite.positions()['net']
    open_pos = [p for p in positions if p['quantity'] != 0]
    
    if not open_pos:
        print("No open positions to test")
        return
    
    pos = open_pos[0]
    symbol = f"{pos['exchange']}:{pos['tradingsymbol']}"
    
    print(f"Testing: {symbol}")
    print(f"Position: {pos['quantity']} @ ₹{pos['average_price']:.2f}")
    print()
    
    # Test Quote API
    print("Testing Quote API (5 attempts with 2s interval)...")
    print()
    
    for i in range(5):
        try:
            quote_data = kite.quote([symbol])
            data = quote_data[symbol]
            
            print(f"Attempt #{i+1}:")
            print(f"  LTP: ₹{data['last_price']:.2f}")
            print(f"  Volume: {data.get('volume', 0):,}")
            print(f"  Last Trade Time: {data.get('last_trade_time', 'N/A')}")
            
            # Depth data
            depth = data.get('depth', {})
            if depth.get('buy'):
                best_bid = depth['buy'][0]['price']
                bid_qty = depth['buy'][0]['quantity']
                print(f"  Best Bid: ₹{best_bid:.2f} ({bid_qty} qty)")
            
            if depth.get('sell'):
                best_ask = depth['sell'][0]['price']
                ask_qty = depth['sell'][0]['quantity']
                print(f"  Best Ask: ₹{best_ask:.2f} ({ask_qty} qty)")
            
            # Calculate P&L
            pnl = (data['last_price'] - pos['average_price']) * pos['quantity']
            print(f"  P&L: ₹{pnl:.2f}")
            print()
            
            if i < 4:
                time.sleep(2)
                
        except Exception as e:
            print(f"❌ Quote API Error: {e}")
            print()
            print("Possible reasons:")
            print("1. Market data subscription not active yet")
            print("2. Need to regenerate access token")
            print("3. Subscription not linked to API key")
            print()
            print("To fix:")
            print("1. Logout and login again: python logout.py && python login.py")
            print("2. Or run: /reconnect in Telegram bot")
            break
    
    print("=" * 70)

if __name__ == "__main__":
    test_quote_api()
