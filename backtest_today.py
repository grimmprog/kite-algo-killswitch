"""
Backtest Today's NIFTY Trade - Trend Continuation with Pullback
Analyzes today's intraday data to find ITM option entry around 12:00 PM
"""
import datetime
import pandas as pd
from connect import get_kite_session
from indicators import calculate_ema, calculate_vwap, calculate_macd, add_candle_metrics

print("=" * 70)
print("NIFTY INTRADAY BACKTEST - TREND CONTINUATION STRATEGY")
print("Target Entry Time: 11:00 - 11:30 AM")
print("=" * 70)

# Initialize Kite session
kite = get_kite_session()

# Get NIFTY 50 instrument token
print("\n1️⃣ Fetching NIFTY 50 instrument...")
instruments = kite.instruments("NSE")
inst_df = pd.DataFrame(instruments)
nifty_row = inst_df[inst_df['tradingsymbol'] == 'NIFTY 50']

if nifty_row.empty:
    print("❌ NIFTY 50 not found")
    exit(1)

nifty_token = nifty_row.iloc[0]['instrument_token']
print(f"✅ NIFTY 50 Token: {nifty_token}")

# Fetch today's intraday data (5-minute candles)
print("\n2️⃣ Fetching today's 5-minute intraday data...")
today = datetime.datetime.now()
start_time = today.replace(hour=9, minute=15, second=0, microsecond=0)
end_time = today.replace(hour=15, minute=30, second=0, microsecond=0)

try:
    data = kite.historical_data(nifty_token, start_time, end_time, interval='5minute')
    df = pd.DataFrame(data)
    
    if df.empty:
        raise Exception("No data from Kite API")
    
    print(f"✅ Fetched {len(df)} candles from {df.iloc[0]['date']} to {df.iloc[-1]['date']}")
    has_intraday = True
        
except Exception as e:
    print(f"⚠️ Kite intraday data not available: {e}")
    print("📊 Using yfinance with 1-hour intervals for simulation...")
    
    has_intraday = False
    
    # Try to get hourly data from yfinance
    import yfinance as yf
    nifty = yf.Ticker("^NSEI")
    
    # Get last 5 days with 1-hour interval
    df = nifty.history(period="5d", interval="1h")
    
    if df.empty:
        print("❌ No data available from yfinance either")
        print("💡 Using daily data for demonstration...")
        df = nifty.history(period="1mo", interval="1d")
    
    if not df.empty:
        print(f"✅ Fetched {len(df)} candles for simulation")
        df = df.rename(columns={
            'Open': 'open', 'High': 'high', 
            'Low': 'low', 'Close': 'close', 'Volume': 'volume'
        })
        df = df.reset_index()
        df = df.rename(columns={'Datetime': 'date'} if 'Datetime' in df.columns else {'Date': 'date'})
    else:
        print("❌ No data available")
        exit(1)


# Calculate indicators
print("\n3️⃣ Calculating technical indicators...")
df = calculate_vwap(df)
df = calculate_ema(df, period=20, target_column='ema_20')
df = calculate_macd(df)
df = add_candle_metrics(df)

print(f"✅ Indicators calculated for {len(df)} candles")

# Find candles around 11:00 - 11:30 AM
print("\n4️⃣ Analyzing price action around 11:00 - 11:30 AM...")

# For intraday: filter around 11:00 - 11:30 AM
# For hourly/daily: use appropriate candles
if 'date' in df.columns and len(df) > 20:
    # Check if we have time component
    if hasattr(df.iloc[0]['date'], 'hour'):
        if has_intraday:
            # 5-minute data - find 11:00 - 11:30 AM candles
            target_candles = df[(df['date'].dt.hour == 11) & (df['date'].dt.minute >= 0) & (df['date'].dt.minute <= 30)]
            print(f"   Target time window: 11:00 - 11:30 AM (5-min candles)")
        else:
            # Hourly data - find 11:00 AM candle
            target_candles = df[df['date'].dt.hour == 11]
            print(f"   Target time window: 11:00 AM hour (hourly candles)")
        
        analysis_start = max(0, target_candles.index[0] - 20) if len(target_candles) > 0 else 20
    else:
        # Daily data - use recent candles
        analysis_start = max(0, len(df) - 10)
        target_candles = df.iloc[analysis_start:]
        print(f"   Using daily data simulation (last 10 days)")
else:
    analysis_start = max(0, len(df) - 10)
    target_candles = df.iloc[analysis_start:]

print(f"✅ Analyzing {len(target_candles)} candles for entry setup")

# Analyze trend and find pullback entry
print("\n5️⃣ Identifying Trend Continuation + Pullback Setup...")

entry_found = False
entry_candle = None
entry_price = None
entry_time = None

for i in range(analysis_start + 20, len(df)):
    curr = df.iloc[i]
    prev = df.iloc[i-1]
    
    # Check for bearish trend
    if curr['close'] < curr['vwap'] and curr['ema_20'] < df.iloc[i-1]['ema_20']:
        # Check for pullback (small body near EMA)
        dist_to_ema = abs(curr['close'] - curr['ema_20']) / curr['close']
        
        if dist_to_ema < 0.005:  # Within 0.5% of EMA
            # Check if previous candle broke lower
            if curr['close'] < prev['low']:
                entry_found = True
                entry_candle = i
                entry_price = curr['close']
                entry_time = curr['date']
                break

if entry_found:
    print(f"✅ ENTRY SIGNAL FOUND!")
    print(f"   Time: {entry_time}")
    print(f"   NIFTY Price: ₹{entry_price:.2f}")
    print(f"   EMA 20: ₹{df.iloc[entry_candle]['ema_20']:.2f}")
    print(f"   VWAP: ₹{df.iloc[entry_candle]['vwap']:.2f}")
else:
    print("⚠️ No clear entry signal found in the analyzed period")
    print("   Using last bearish candle for simulation...")
    
    # Find last bearish candle
    for i in range(len(df)-1, analysis_start, -1):
        if df.iloc[i]['close'] < df.iloc[i]['vwap']:
            entry_candle = i
            entry_price = df.iloc[i]['close']
            entry_time = df.iloc[i]['date']
            break
    
    if entry_candle is None or entry_price is None:
        # Use last candle as fallback
        entry_candle = len(df) - 1
        entry_price = df.iloc[-1]['close']
        entry_time = df.iloc[-1]['date']
    
    print(f"   Using candle at: {entry_time}")
    print(f"   NIFTY Price: ₹{entry_price:.2f}")


# Calculate ITM strike for PE option
print("\n6️⃣ Selecting ITM PUT Option...")

# Round to nearest 50 (NIFTY strike step)
strike_step = 50
atm_strike = round(entry_price / strike_step) * strike_step

# ITM PE = strike above current price
itm_strike = atm_strike + (2 * strike_step)  # 100 points ITM

print(f"   ATM Strike: {atm_strike}")
print(f"   Selected ITM Strike: {itm_strike} PE")
print(f"   ITM by: ₹{itm_strike - entry_price:.2f}")

# Estimate option premium (simplified)
# ITM premium ≈ Intrinsic Value + Time Value
intrinsic_value = itm_strike - entry_price
time_value = 20  # Approximate time value
option_premium = intrinsic_value + time_value

print(f"   Estimated Premium: ₹{option_premium:.2f}")

# Calculate position details
lot_size = 65  # NIFTY lot size
quantity = lot_size
investment = option_premium * quantity

print(f"\n7️⃣ Position Details:")
print(f"   Symbol: NIFTY {itm_strike} PE")
print(f"   Entry Price: ₹{option_premium:.2f}")
print(f"   Quantity: {quantity}")
print(f"   Investment: ₹{investment:,.2f}")

# Calculate stop loss and target
stop_loss_candle = df.iloc[entry_candle - 1]
sl_price = stop_loss_candle['high']
sl_points = sl_price - entry_price

# For options: SL in premium terms
sl_premium = option_premium - (sl_points * 0.5)  # Options move ~50% of underlying
target_premium = option_premium + (abs(sl_points) * 0.5)  # 1:1 RR

print(f"\n8️⃣ Risk Management:")
print(f"   Stop Loss (NIFTY): ₹{sl_price:.2f}")
print(f"   Stop Loss (Premium): ₹{sl_premium:.2f}")
print(f"   Target (Premium): ₹{target_premium:.2f}")
print(f"   Risk per lot: ₹{(option_premium - sl_premium) * quantity:,.2f}")
print(f"   Reward per lot: ₹{(target_premium - option_premium) * quantity:,.2f}")

# Simulate outcome using remaining candles
print(f"\n9️⃣ Simulating Trade Outcome...")

if entry_candle < len(df) - 1:
    max_profit = 0
    max_loss = 0
    exit_reason = "End of Day"
    exit_price = option_premium
    
    for i in range(entry_candle + 1, len(df)):
        candle = df.iloc[i]
        
        # Estimate option price based on NIFTY movement
        nifty_move = entry_price - candle['close']
        option_move = nifty_move * 0.5  # Simplified delta
        current_premium = option_premium + option_move
        
        pnl = (current_premium - option_premium) * quantity
        
        if pnl > max_profit:
            max_profit = pnl
        if pnl < max_loss:
            max_loss = pnl
        
        # Check stop loss
        if candle['high'] >= sl_price:
            exit_price = sl_premium
            exit_reason = "Stop Loss Hit"
            break
        
        # Check target
        if current_premium >= target_premium:
            exit_price = target_premium
            exit_reason = "Target Hit"
            break
        
        # Last candle
        if i == len(df) - 1:
            exit_price = current_premium
    
    final_pnl = (exit_price - option_premium) * quantity
    
    print(f"   Exit Reason: {exit_reason}")
    print(f"   Exit Price: ₹{exit_price:.2f}")
    print(f"   Final P&L: ₹{final_pnl:,.2f}")
    print(f"   Max Profit Seen: ₹{max_profit:,.2f}")
    print(f"   Max Loss Seen: ₹{max_loss:,.2f}")
    
    if final_pnl > 0:
        print(f"   ✅ PROFITABLE TRADE (+{(final_pnl/investment)*100:.2f}%)")
    else:
        print(f"   ❌ LOSS ({(final_pnl/investment)*100:.2f}%)")
else:
    print("   ⚠️ No candles after entry to simulate outcome")

print("\n" + "=" * 70)
print("BACKTEST COMPLETE")
print("=" * 70)
