"""
Test Historical Data API Access
Checks if your Kite app has historical data permission enabled
"""
from connect import get_kite_session
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_historical_data():
    print("=" * 60)
    print("TESTING HISTORICAL DATA API ACCESS")
    print("=" * 60)
    print()
    
    try:
        # Get Kite session
        print("1. Connecting to Kite API...")
        kite = get_kite_session()
        print("   ✅ Connected")
        print()
        
        # Get NIFTY 50 instrument
        print("2. Fetching NIFTY 50 instrument...")
        instruments = kite.instruments('NSE')
        nifty = [i for i in instruments if i['tradingsymbol'] == 'NIFTY 50']
        
        if not nifty:
            print("   ❌ NIFTY 50 not found")
            return False
        
        token = nifty[0]['instrument_token']
        print(f"   ✅ Found NIFTY 50 (Token: {token})")
        print()
        
        # Try to fetch historical data
        print("3. Fetching historical data...")
        to_date = datetime.now()
        from_date = to_date - timedelta(days=1)
        
        data = kite.historical_data(
            token, 
            from_date, 
            to_date, 
            '5minute'
        )
        
        print(f"   ✅ SUCCESS! Received {len(data)} candles")
        print()
        
        # Show sample data
        if data:
            print("4. Sample candle data:")
            latest = data[-1]
            print(f"   Date: {latest['date']}")
            print(f"   Open: {latest['open']}")
            print(f"   High: {latest['high']}")
            print(f"   Low: {latest['low']}")
            print(f"   Close: {latest['close']}")
            print(f"   Volume: {latest['volume']}")
        
        print()
        print("=" * 60)
        print("✅ HISTORICAL DATA API IS WORKING!")
        print("=" * 60)
        print()
        print("Your bot can now:")
        print("  ✅ Scan NIFTY & BANKNIFTY")
        print("  ✅ Calculate technical indicators")
        print("  ✅ Generate trade signals")
        print("  ✅ Run fully automated")
        print()
        print("Start the bot:")
        print("  python main.py")
        print()
        
        return True
        
    except Exception as e:
        error_msg = str(e)
        
        print()
        print("=" * 60)
        print("❌ HISTORICAL DATA API NOT WORKING")
        print("=" * 60)
        print()
        print(f"Error: {error_msg}")
        print()
        
        if "Insufficient permission" in error_msg:
            print("SOLUTION:")
            print("=" * 60)
            print()
            print("Historical data permission is not enabled in your Kite app.")
            print()
            print("Follow these steps:")
            print()
            print("1. Go to: https://developers.kite.trade/")
            print("2. Login with Zerodha credentials")
            print("3. Click 'My Apps'")
            print("4. Edit your app")
            print("5. Enable 'Historical data' permission")
            print("6. Save changes")
            print("7. Wait 10 minutes")
            print("8. Generate new token: python login.py")
            print("9. Run this test again")
            print()
            print("Detailed guide: FIX_HISTORICAL_DATA.md")
            print()
        else:
            print("Other possible issues:")
            print("  - Access token expired (run: python login.py)")
            print("  - Network connectivity")
            print("  - Kite API down")
            print()
        
        return False

if __name__ == "__main__":
    test_historical_data()
