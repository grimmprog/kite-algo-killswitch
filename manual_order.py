"""
Manual Order Placement Script
Place a single order with custom parameters
"""
from connect import get_kite_session
from kiteconnect import KiteConnect
import config

def find_option_symbol(kite, index, strike, option_type, expiry_date=None):
    """
    Find the exact trading symbol for an option
    index: "NIFTY" or "BANKNIFTY"
    strike: strike price (e.g., 25500)
    option_type: "CE" or "PE"
    expiry_date: "YYMMDD" format, if None uses nearest weekly expiry
    """
    instruments = kite.instruments("NFO")
    
    # Filter for the index options
    options = [i for i in instruments if i['name'] == index and i['instrument_type'] == option_type]
    
    # Filter by strike
    options = [i for i in options if i['strike'] == strike]
    
    if not options:
        print(f"❌ No options found for {index} {strike} {option_type}")
        return None
    
    # Sort by expiry and get the nearest
    options.sort(key=lambda x: x['expiry'])
    
    if expiry_date:
        # Find specific expiry
        for opt in options:
            if opt['expiry'].strftime('%y%m%d') == expiry_date:
                return opt['tradingsymbol']
    
    # Return nearest expiry
    return options[0]['tradingsymbol']

def place_order_with_gtt(kite, symbol, quantity, transaction_type):
    """
    Place a regular order and then set GTT for target and stop loss
    """
    try:
        # Step 1: Place the main order
        print("Placing main order...")
        order_id = kite.place_order(
            variety=kite.VARIETY_REGULAR,
            exchange=kite.EXCHANGE_NFO,
            tradingsymbol=symbol,
            transaction_type=transaction_type,
            quantity=quantity,
            product=kite.PRODUCT_MIS,
            order_type=kite.ORDER_TYPE_MARKET
        )
        
        print(f"✅ Main order placed: {order_id}")
        
        # Wait a moment for order to execute
        import time
        time.sleep(2)
        
        # Get order details to confirm execution
        orders = kite.orders()
        order_details = [o for o in orders if o['order_id'] == order_id]
        
        if not order_details or order_details[0]['status'] != 'COMPLETE':
            print("⚠️  Order not yet executed. Please set GTT manually.")
            return order_id, None, None
        
        avg_price = float(order_details[0]['average_price'])
        print(f"Order executed at: ₹{avg_price}")
        
        # Step 2: Set GTT for Target (exit at +2 points)
        target_price = avg_price + 2
        print(f"\nSetting GTT for Target at ₹{target_price}...")
        
        exit_type = "SELL" if transaction_type == "BUY" else "BUY"
        
        target_gtt = kite.place_gtt(
            trigger_type=kite.GTT_TYPE_SINGLE,
            tradingsymbol=symbol,
            exchange=kite.EXCHANGE_NFO,
            trigger_values=[target_price],
            last_price=avg_price,
            orders=[{
                "transaction_type": exit_type,
                "quantity": quantity,
                "product": kite.PRODUCT_MIS,
                "order_type": kite.ORDER_TYPE_LIMIT,
                "price": target_price
            }]
        )
        print(f"✅ Target GTT placed: {target_gtt['trigger_id']}")
        
        # Step 3: Set GTT for Stop Loss (exit at -2 points)
        sl_price = avg_price - 2
        print(f"Setting GTT for Stop Loss at ₹{sl_price}...")
        
        sl_gtt = kite.place_gtt(
            trigger_type=kite.GTT_TYPE_SINGLE,
            tradingsymbol=symbol,
            exchange=kite.EXCHANGE_NFO,
            trigger_values=[sl_price],
            last_price=avg_price,
            orders=[{
                "transaction_type": exit_type,
                "quantity": quantity,
                "product": kite.PRODUCT_MIS,
                "order_type": kite.ORDER_TYPE_LIMIT,
                "price": sl_price
            }]
        )
        print(f"✅ Stop Loss GTT placed: {sl_gtt['trigger_id']}")
        
        return order_id, target_gtt['trigger_id'], sl_gtt['trigger_id']
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, None, None

def main():
    print("=" * 60)
    print("MANUAL ORDER PLACEMENT")
    print("=" * 60)
    
    # Get Kite session
    kite = get_kite_session()
    
    # Default values for your request
    index = "NIFTY"
    strike = 25500
    option_type = "PE"
    quantity = 65  # 1 lot of NIFTY = 65
    transaction_type = "BUY"
    
    print(f"\nFinding option symbol for {index} {strike} {option_type}...")
    symbol = find_option_symbol(kite, index, strike, option_type)
    
    if not symbol:
        print("❌ Could not find option symbol")
        return
    
    print(f"✅ Found: {symbol}")
    
    # Get current price
    try:
        quote = kite.quote(f"NFO:{symbol}")
        ltp = quote[f"NFO:{symbol}"]['last_price']
        print(f"Current Price: ₹{ltp}")
    except Exception as e:
        print(f"⚠️  Could not fetch price: {e}")
        ltp = None
    
    print("\n" + "=" * 60)
    print("ORDER DETAILS")
    print("=" * 60)
    print(f"Symbol: {symbol}")
    print(f"Type: {transaction_type}")
    print(f"Quantity: {quantity} (1 lot)")
    print(f"Current Price: ₹{ltp if ltp else 'N/A'}")
    print(f"Target: +2 points (₹{ltp + 2 if ltp else 'N/A'})")
    print(f"Stop Loss: -2 points (₹{ltp - 2 if ltp else 'N/A'})")
    print("\nNote: Using GTT (Good Till Triggered) for target & SL")
    print("=" * 60)
    
    confirm = input("\nPlace this order? (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("Order cancelled.")
        return
    
    print("\nPlacing order with GTT...")
    order_id, target_gtt, sl_gtt = place_order_with_gtt(kite, symbol, quantity, transaction_type)
    
    if order_id:
        print(f"\n{'=' * 60}")
        print("✅ ORDER PLACED SUCCESSFULLY!")
        print(f"{'=' * 60}")
        print(f"Order ID: {order_id}")
        if target_gtt:
            print(f"Target GTT ID: {target_gtt}")
        if sl_gtt:
            print(f"Stop Loss GTT ID: {sl_gtt}")
        print(f"{'=' * 60}")
        
        # Ask if user wants to start active monitoring
        print("\n⚠️  GTT orders can have slippage in fast markets.")
        monitor = input("Start active position monitor for better SL protection? (y/n): ").strip().lower()
        
        if monitor == 'y':
            print("\nStarting position monitor...")
            from position_monitor import monitor_position
            
            # Get the executed price
            import time
            time.sleep(2)
            orders = kite.orders()
            order_details = [o for o in orders if o['order_id'] == order_id]
            
            if order_details and order_details[0]['status'] == 'COMPLETE':
                avg_price = float(order_details[0]['average_price'])
                monitor_position(symbol, avg_price, target_points=2, sl_points=2, check_interval=1)
            else:
                print("Could not get execution price. Please run position_monitor.py manually.")
        else:
            print("\nGTT orders are active. Monitor your position in Kite app.")
            
        if not target_gtt or not sl_gtt:
            print("\n⚠️  GTT orders not set automatically.")
            print("Please set them manually in Kite:")
            print(f"   Target: ₹{ltp + 2 if ltp else 'N/A'}")
            print(f"   Stop Loss: ₹{ltp - 2 if ltp else 'N/A'}")
    else:
        print("\n❌ Order placement failed")

if __name__ == "__main__":
    main()
