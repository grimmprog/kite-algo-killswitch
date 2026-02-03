"""
Test NSEpy Integration for Free Historical Data
"""
import sys
import datetime

print("=" * 60)
print("TESTING NSEPY INTEGRATION")
print("=" * 60)

# Test 1: Check if NSEpy is installed
print("\n1️⃣ Checking NSEpy installation...")
try:
    from nsepy import get_history
    print("✅ NSEpy is installed")
except ImportError as e:
    print("❌ NSEpy NOT installed")
    print(f"Error: {e}")
    print("\nInstall with:")
    print("  pip install nsepy")
    print("  OR")
    print("  pip install -r requirements.txt")
    sys.exit(1)

# Test 2: Fetch NIFTY historical data
print("\n2️⃣ Fetching NIFTY historical data (last 5 days)...")
try:
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=5)
    
    nifty_data = get_history(
        symbol="NIFTY",
        start=start_date,
        end=end_date,
        index=True
    )
    
    if nifty_data is not None and not nifty_data.empty:
        print(f"✅ Fetched {len(nifty_data)} days of NIFTY data")
        print("\nLatest data:")
        latest = nifty_data.iloc[-1]
        print(f"   Date: {nifty_data.index[-1]}")
        print(f"   Open: ₹{latest['Open']:.2f}")
        print(f"   High: ₹{latest['High']:.2f}")
        print(f"   Low: ₹{latest['Low']:.2f}")
        print(f"   Close: ₹{latest['Close']:.2f}")
        print(f"   Volume: {latest['Volume']:,.0f}")
    else:
        print("⚠️ No data returned (market might be closed or weekend)")
        
except Exception as e:
    print(f"❌ Error fetching NIFTY data: {e}")
    print("Note: Data might not be available on weekends/holidays")

# Test 3: Fetch NIFTY BANK historical data
print("\n3️⃣ Fetching NIFTY BANK historical data (last 5 days)...")
try:
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=5)
    
    banknifty_data = get_history(
        symbol="NIFTY BANK",
        start=start_date,
        end=end_date,
        index=True
    )
    
    if banknifty_data is not None and not banknifty_data.empty:
        print(f"✅ Fetched {len(banknifty_data)} days of NIFTY BANK data")
        print("\nLatest data:")
        latest = banknifty_data.iloc[-1]
        print(f"   Date: {banknifty_data.index[-1]}")
        print(f"   Open: ₹{latest['Open']:.2f}")
        print(f"   High: ₹{latest['High']:.2f}")
        print(f"   Low: ₹{latest['Low']:.2f}")
        print(f"   Close: ₹{latest['Close']:.2f}")
        print(f"   Volume: {latest['Volume']:,.0f}")
    else:
        print("⚠️ No data returned (market might be closed or weekend)")
        
except Exception as e:
    print(f"❌ Error fetching NIFTY BANK data: {e}")
    print("Note: Data might not be available on weekends/holidays")

# Test 4: Fetch longer historical data (30 days for indicators)
print("\n4️⃣ Fetching 30 days of data for indicators...")
try:
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(days=30)
    
    nifty_30d = get_history(
        symbol="NIFTY",
        start=start_date,
        end=end_date,
        index=True
    )
    
    if nifty_30d is not None and not nifty_30d.empty:
        print(f"✅ Fetched {len(nifty_30d)} days of data")
        print("   Sufficient for EMA(20), MACD, and other indicators")
    else:
        print("⚠️ No data returned")
        
except Exception as e:
    print(f"❌ Error: {e}")

# Test 5: Test scanner integration
print("\n5️⃣ Testing Scanner Integration...")
try:
    from scanner import market_scanner
    
    print("Attempting to scan NIFTY 50...")
    df = market_scanner.fetch_ohlc("NIFTY 50")
    
    if not df.empty:
        print(f"✅ Scanner fetched data: {len(df)} candles")
        print(f"   Latest Close: ₹{df.iloc[-1]['close']:.2f}")
    else:
        print("⚠️ Scanner returned empty data")
        
except Exception as e:
    print(f"❌ Scanner test failed: {e}")

print("\n" + "=" * 60)
print("NSEPY TEST COMPLETE")
print("=" * 60)
print("\n📝 Notes:")
print("- NSEpy fetches data from NSE website (FREE)")
print("- Historical data available for backtesting")
print("- No API key or subscription required")
print("- Data available for past trading days")
print("\n⚠️ Limitations:")
print("- NSEpy provides daily OHLC data (not 5-minute intraday)")
print("- For live trading, strategy uses daily candles")
print("- Data only available for past trading days")
print("- Weekend/holiday data not available")
print("\n✅ Advantages:")
print("- Completely FREE (no subscription)")
print("- Sufficient for daily/swing trading strategies")
print("- Works with trend analysis and indicators")
print("=" * 60)

