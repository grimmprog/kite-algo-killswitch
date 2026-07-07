"""Fetch capital, trades, positions, and P&L from Kite."""
import sys
sys.path.insert(0, '.')
from connect import get_kite_session
import json

kite = get_kite_session()

print("=" * 60)
print("ACCOUNT SUMMARY")
print("=" * 60)

# 1. Margins / Capital
print("\n--- MARGINS / CAPITAL ---")
try:
    margins = kite.margins()
    equity = margins.get("equity", {})
    commodity = margins.get("commodity", {})
    
    print(f"  Equity Available:   Rs {equity.get('available', {}).get('live_balance', 0):,.2f}")
    print(f"  Equity Net:         Rs {equity.get('net', 0):,.2f}")
    print(f"  Equity Used:        Rs {equity.get('utilised', {}).get('debits', 0):,.2f}")
    print(f"  Commodity Net:      Rs {commodity.get('net', 0):,.2f}")
    print(f"\n  Full equity margins:")
    for key, val in equity.get('available', {}).items():
        print(f"    {key}: {val}")
except Exception as e:
    print(f"  Error: {e}")

# 2. Today's Trades
print("\n--- TODAY'S TRADES ---")
try:
    trades = kite.trades()
    print(f"  Total trades today: {len(trades)}")
    if trades:
        for t in trades:
            side = t['transaction_type']
            symbol = t['tradingsymbol']
            qty = t['quantity']
            price = t['average_price']
            print(f"  {side} {symbol} qty={qty} @ Rs {price:.2f}")
    else:
        print("  No trades today.")
except Exception as e:
    print(f"  Error: {e}")

# 3. Positions & P&L
print("\n--- POSITIONS & P&L ---")
try:
    positions = kite.positions()
    net_positions = positions.get("net", [])
    day_positions = positions.get("day", [])
    
    total_pnl = 0
    print(f"  Net positions: {len(net_positions)}")
    print(f"  Day positions: {len(day_positions)}")
    
    if day_positions:
        print("\n  Day Positions:")
        for p in day_positions:
            pnl = p.get('pnl', 0)
            total_pnl += pnl
            symbol = p['tradingsymbol']
            qty = p['quantity']
            buy_price = p.get('average_price', 0)
            ltp = p.get('last_price', 0)
            print(f"    {symbol}: qty={qty}, avg={buy_price:.2f}, ltp={ltp:.2f}, P&L=Rs {pnl:.2f}")
    
    if net_positions:
        print("\n  Net Positions:")
        for p in net_positions:
            pnl = p.get('pnl', 0)
            if p not in day_positions:
                total_pnl += pnl
            symbol = p['tradingsymbol']
            qty = p['quantity']
            ltp = p.get('last_price', 0)
            print(f"    {symbol}: qty={qty}, ltp={ltp:.2f}, P&L=Rs {pnl:.2f}")
    
    print(f"\n  TOTAL P&L TODAY: Rs {total_pnl:,.2f}")
except Exception as e:
    print(f"  Error: {e}")

# 4. Orders
print("\n--- TODAY'S ORDERS ---")
try:
    orders = kite.orders()
    print(f"  Total orders: {len(orders)}")
    if orders:
        for o in orders[:10]:
            status = o['status']
            side = o['transaction_type']
            symbol = o['tradingsymbol']
            qty = o['quantity']
            price = o.get('average_price', o.get('price', 0))
            print(f"  [{status}] {side} {symbol} qty={qty} @ {price}")
except Exception as e:
    print(f"  Error: {e}")

print("\n" + "=" * 60)
