"""
Test yfinance Integration for Free Historical Data
"""
import sys
import datetime

print("=" * 60)
print("TESTING YFINANCE INTEGRATION")
print("=" * 60)

# Test 1: Check if yfinance is installed
print("\n1️⃣ Checking yfinance installation...")
try:
    import yfinance as yf
    print("✅ yfinance is installed")
except ImportError as e:
    print("❌ yfinance NOT installed")
    print(f"Error: {e}")
    print("\nInstall with:")
    print("  pip install yfinance")
    print("  OR")
    print("  pip install -r requirements.txt")
    sys.exit(1)

# Test 2: Fetch NIFTY 50 data
print("\n2️⃣ Fetching NIFTY 50 data (^NSEI)...")
try:
    nifty = yf.Ticker("^NSEI")
    df = nifty.history(period="1mo", interval="1d")
    
    if not df.empty:
        print(f"✅ Fetched {len(df)} days of NIFTY 50 data")
        print("\nLatest data:")
        latest = df.iloc[-1]
        print(f"   Date: {df.index[-1].strftime('%Y-%m-%d')}")
        print(f"   Open: ₹{latest['Open']:.2f}")
        print(f"   High: ₹{latest['High']:.2f}")
        print(f"   Low: ₹{latest['Low']:.2f}")
        print(f"   Close: ₹{latest['Close']:.2f}")
        print(f"   Volume: {latest['Volume']:,.0f}")
    else:
        print("⚠️ No data returned")
        
except Exception as e:
    print(f"❌ Error fetching NIFTY 50: {e}")

# Test 3: Fetch NIFTY BANK data
print("\n3️⃣ Fetching NIFTY BANK data (^NSEBANK)...")
try:
    banknifty = yf.Ticker("^NSEBANK")
    df = banknifty.history(period="1mo", interval="1d")
    
    if not df.empty:
        print(f"✅ Fetched {len(df)} days of NIFTY BANK data")
        print("\nLatest data:")
        latest = df.iloc[-1]
        print(f"   Date: {df.index[-1].strftime('%Y-%m-%d')}")
        print(f"   Open: ₹{latest['Open']:.2f}")
        print(f"   High: ₹{latest['High']:.2f}")
        print(f"   Low: ₹{latest['Low']:.2f}")
        print(f"   Close: ₹{latest['Close']:.2f}")
        print(f"   Volume: {latest['Volume']:,.0f}")
    else:
        print("⚠️ No data returned")
        
except Exception as e:
    print(f"❌ Error fetching NIFTY BANK: {e}")

# Test 4: Test scanner integration
print("\n4️⃣ Testing Scanner Integration...")
try:
    from scanner import market_scanner
    
    print("Attempting to scan NIFTY 50...")
    df = market_scanner.fetch_ohlc("NIFTY 50")
    
    if not df.empty:
        print(f"✅ Scanner fetched data: {len(df)} candles")
        print(f"   Latest Close: ₹{df.iloc[-1]['close']:.2f}")
        print(f"   Date Range: {df.iloc[0]['date'].strftime('%Y-%m-%d')} to {df.iloc[-1]['date'].strftime('%Y-%m-%d')}")
    else:
        print("⚠️ Scanner returned empty data")
        
except Exception as e:
    print(f"❌ Scanner test failed: {e}")

print("\n" + "=" * 60)
print("YFINANCE TEST COMPLETE")
print("=" * 60)
print("\n✅ Advantages:")
print("- Completely FREE (no subscription)")
print("- Very reliable (Yahoo Finance)")
print("- No API key required")
print("- Works globally")
print("- Daily OHLC data for indices")
print("\n📝 Usage:")
print("- NIFTY 50: ^NSEI")
print("- NIFTY BANK: ^NSEBANK")
print("- Sufficient for daily/swing trading strategies")
print("- Works with trend analysis and indicators")
print("\n⚠️ Note:")
print("- Provides daily data (not 5-minute intraday)")
print("- Perfect for end-of-day strategies")
print("- Data available for past trading days")
print("=" * 60)
