"""
Position Monitor - Active SL/Target Management
Monitors your position in real-time and exits immediately when SL or target is hit
More reliable than GTT for fast-moving markets
"""
from connect import get_kite_session
import time
import sys

def get_position_details(kite, symbol):
    """Get current position for a symbol"""
    try:
        positions = kite.positions()['net']
        for pos in positions:
            if pos['tradingsymbol'] == symbol and pos['quantity'] != 0:
                return pos
        return None
    except Exception as e:
        print(f"Error fetching positions: {e}")
        return None

def get_ltp(kite, symbol):
    """Get Last Traded Price"""
    try:
        quote = kite.quote(f"NFO:{symbol}")
        return quote[f"NFO:{symbol}"]['last_price']
    except Exception as e:
        print(f"Error fetching LTP: {e}")
        return None

def exit_position(kite, symbol, quantity, transaction_type):
    """Exit position with market order"""
    try:
        order_id = kite.place_order(
            variety=kite.VARIETY_REGULAR,
            exchange=kite.EXCHANGE_NFO,
            tradingsymbol=symbol,
            transaction_type=transaction_type,
            quantity=abs(quantity),
            product=kite.PRODUCT_MIS,
            order_type=kite.ORDER_TYPE_MARKET
        )
        return order_id
    except Exception as e:
        print(f"❌ Exit order failed: {e}")
        return None

def monitor_position(symbol, entry_price, target_points, sl_points, check_interval=1):
    """
    Monitor position and exit when target or SL is hit
    check_interval: seconds between checks (default 1 second)
    """
    kite = get_kite_session()
    
    target_price = entry_price + target_points
    sl_price = entry_price - sl_points
    
    print("=" * 60)
    print("POSITION MONITOR STARTED")
    print("=" * 60)
    print(f"Symbol: {symbol}")
    print(f"Entry Price: ₹{entry_price}")
    print(f"Target: ₹{target_price} (+{target_points} points)")
    print(f"Stop Loss: ₹{sl_price} (-{sl_points} points)")
    print(f"Check Interval: {check_interval} second(s)")
    print("=" * 60)
    print("\nMonitoring... (Press Ctrl+C to stop)\n")
    
    highest_price = entry_price
    
    try:
        while True:
            # Get current position
            position = get_position_details(kite, symbol)
            
            if not position or position['quantity'] == 0:
                print("\n⚠️  Position closed or not found. Stopping monitor.")
                break
            
            # Get current price
            ltp = get_ltp(kite, symbol)
            
            if not ltp:
                time.sleep(check_interval)
                continue
            
            # Track highest price for trailing info
            if ltp > highest_price:
                highest_price = ltp
            
            # Calculate P&L
            pnl = position['pnl']
            pnl_percent = ((ltp - entry_price) / entry_price) * 100
            
            # Print status
            print(f"\rLTP: ₹{ltp:.2f} | P&L: ₹{pnl:.2f} ({pnl_percent:+.2f}%) | High: ₹{highest_price:.2f}", end='', flush=True)
            
            # Check Target
            if ltp >= target_price:
                print(f"\n\n🎯 TARGET HIT at ₹{ltp}!")
                print("Exiting position with market order...")
                
                exit_type = "SELL" if position['quantity'] > 0 else "BUY"
                order_id = exit_position(kite, symbol, position['quantity'], exit_type)
                
                if order_id:
                    print(f"✅ Exit order placed: {order_id}")
                    print(f"Final P&L: ₹{pnl:.2f}")
                else:
                    print("❌ Exit order failed! Please exit manually!")
                break
            
            # Check Stop Loss
            if ltp <= sl_price:
                print(f"\n\n🛑 STOP LOSS HIT at ₹{ltp}!")
                print("Exiting position with market order...")
                
                exit_type = "SELL" if position['quantity'] > 0 else "BUY"
                order_id = exit_position(kite, symbol, position['quantity'], exit_type)
                
                if order_id:
                    print(f"✅ Exit order placed: {order_id}")
                    print(f"Final P&L: ₹{pnl:.2f}")
                else:
                    print("❌ Exit order failed! Please exit manually!")
                break
            
            time.sleep(check_interval)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Monitor stopped by user.")
        print("Position is still open. Exit manually if needed.")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        print("Position may still be open. Please check manually!")

def main():
    print("=" * 60)
    print("POSITION MONITOR")
    print("=" * 60)
    
    # Get position details from user
    symbol = input("Enter symbol (e.g., NIFTY2612025500PE): ").strip()
    entry_price = float(input("Enter entry price: "))
    target_points = float(input("Enter target points (e.g., 2): "))
    sl_points = float(input("Enter stop loss points (e.g., 2): "))
    
    # Optional: faster checking for volatile markets
    fast_mode = input("Fast mode (0.5s checks) for volatile market? (y/n): ").strip().lower()
    check_interval = 0.5 if fast_mode == 'y' else 1
    
    monitor_position(symbol, entry_price, target_points, sl_points, check_interval)

if __name__ == "__main__":
    main()
