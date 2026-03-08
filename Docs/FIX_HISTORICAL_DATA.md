# Fix "Insufficient Permission" Error

The historical data API is **FREE** and included with Kite Connect. The error means your API app needs permission configuration.

## Solution: Enable Historical Data Permission

### Step 1: Login to Kite Developer Console

1. Go to: https://developers.kite.trade/
2. Login with your Zerodha credentials
3. Click on "My Apps"

### Step 2: Edit Your App

1. Find your app (the one with API key: `tobi70rsjs4zzqcb`)
2. Click "Edit" or the app name

### Step 3: Enable Permissions

Look for **"Permissions"** or **"API Permissions"** section and ensure these are checked:

- ✅ **Historical data** (This is what you need!)
- ✅ Place orders
- ✅ Modify orders
- ✅ Cancel orders
- ✅ View holdings
- ✅ View positions
- ✅ View margins

### Step 4: Save Changes

1. Click "Save" or "Update"
2. Wait 5-10 minutes for changes to propagate
3. Generate a new access token:
   ```bash
   python login.py
   ```

### Step 5: Test

```bash
python test_connection.py
```

Then try running the bot:
```bash
python main.py
```

## Alternative: Check App Status

Sometimes the app might be in "Development" mode with limited permissions.

### Check App Status:

1. Go to https://developers.kite.trade/
2. Check if your app is:
   - **Development** - Limited to your account only
   - **Published** - Can be used by others (not needed for personal use)

### If in Development Mode:

This is fine for personal trading! Just make sure:
1. Historical data permission is enabled
2. You're using the correct API key
3. Access token is fresh (generated today)

## Common Issues:

### Issue 1: Wrong API Key
**Check:** Your `.env` file has the correct API key
```bash
# View your API key
cat .env | grep KITE_API_KEY
```

### Issue 2: Expired Access Token
**Fix:** Generate new token daily
```bash
python login.py
```

### Issue 3: App Not Approved
**Check:** App status on developer console
- Development apps work fine for personal use
- No approval needed for personal trading

### Issue 4: Rate Limiting
**Symptom:** Works sometimes, fails other times
**Fix:** Add delays between API calls (already implemented)

## Test Historical Data Access

Run this test:

```bash
python -c "
from connect import get_kite_session
from datetime import datetime, timedelta

kite = get_kite_session()

# Get NIFTY 50 instrument token
instruments = kite.instruments('NSE')
nifty = [i for i in instruments if i['tradingsymbol'] == 'NIFTY 50'][0]
token = nifty['instrument_token']

# Try to fetch historical data
to_date = datetime.now()
from_date = to_date - timedelta(days=1)

try:
    data = kite.historical_data(token, from_date, to_date, '5minute')
    print(f'✅ SUCCESS! Got {len(data)} candles')
    print(f'Latest candle: {data[-1]}')
except Exception as e:
    print(f'❌ ERROR: {e}')
    print('Follow the steps above to enable historical data permission')
"
```

## Expected Result:

**Success:**
```
✅ SUCCESS! Got 75 candles
Latest candle: {'date': '2026-01-21T15:25:00+0530', 'open': 23500.0, ...}
```

**Still Failing:**
```
❌ ERROR: Insufficient permission for that call
```

If still failing after enabling permissions:
1. Wait 10-15 minutes
2. Generate new access token
3. Try again
4. Contact Zerodha support if issue persists

## Important Notes:

- ✅ Historical data is **FREE** with Kite Connect
- ✅ No additional subscription needed
- ✅ Just need to enable permission in app settings
- ✅ Works immediately after enabling (may take 5-10 min)

## After Fixing:

Once historical data works, your bot will:
- ✅ Scan NIFTY & BANKNIFTY automatically
- ✅ Generate trade signals
- ✅ Calculate technical indicators
- ✅ Fully automated trading

---

**Current Issue:** Historical data permission not enabled

**Fix:** Enable in Kite Developer Console → Your App → Permissions → Historical Data

**Time to Fix:** 5 minutes + 10 minutes propagation = 15 minutes total

Let me know once you've enabled it and we'll test!
