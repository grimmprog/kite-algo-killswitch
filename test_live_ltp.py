#!/usr/bin/env python3
"""
Test live LTP fetching to see if Kite API is returning stale data
"""
from connect import get_kite_session
import time

def test_live_ltp():
    """Test LTP API multiple times"""
    print("=" * 70)
    print("TESTING LIVE LTP API")
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
    print(f"Position Quantity: {pos['quantity']}")
    print(f"Average Price: ₹{pos['average_price']:.2f}")
    print()
    print("Fetching LTP 5 times with 2 second intervals...")
    print()
    
    for i in range(5):
        print(f"Attempt #{i+1}:")
        
        # Method 1: positions API
        positions_data = kite.positions()['net']
        pos_data = [p for p in positions_data if p['tradingsymbol'] == pos['tradingsymbol']][0]
        positions_ltp = pos_data['last_price']
        positions_pnl = pos_data['pnl']
        
        # Method 2: ltp API
        ltp_data = kite.ltp([symbol])
        ltp_api_price = ltp_data[symbol]['last_price']
        
        # Method 3: quote API (most detailed)
        try:
            quote_data = kite.quote([symbol])
            quote_ltp = quote_data[symbol]['last_price']
            quote_depth = quote_data[symbol]['depth']
            best_bid = quote_depth['buy'][0]['price'] if quote_depth['buy'] else 0
            best_ask = quote_depth['sell'][0]['price'] if quote_depth['sell'] else 0
        except:
            quote_ltp = None
            best_bid = 0
            best_ask = 0
        
        # Calculate P&L
        manual_pnl = (ltp_api_price - pos['average_price']) * pos['quantity']
        
        print(f"  Positions API LTP: ₹{positions_ltp:.2f} | P&L: ₹{positions_pnl:.2f}")
        print(f"  LTP API:           ₹{ltp_api_price:.2f} | P&L: ₹{manual_pnl:.2f}")
        if quote_ltp:
            manual_pnl_quote = (quote_ltp - pos['average_price']) * pos['quantity']
            print(f"  Quote API LTP:     ₹{quote_ltp:.2f} | P&L: ₹{manual_pnl_quote:.2f}")
            print(f"  Best Bid/Ask:      ₹{best_bid:.2f} / ₹{best_ask:.2f}")
        
        print()
        
        if i < 4:
            time.sleep(2)
    
    print("=" * 70)
    print("ANALYSIS:")
    print("- If all 5 attempts show same LTP → Kite API is stale")
    print("- If LTP changes → API is live, bot code issue")
    print("- Quote API is most accurate (includes bid/ask)")
    print("=" * 70)

if __name__ == "__main__":
    test_live_ltp()
