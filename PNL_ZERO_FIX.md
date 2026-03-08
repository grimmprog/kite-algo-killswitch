# P&L Shows Zero After Logout/Restart - FIX

## Problem
After using `/logout` and service restart, the bot shows ₹0.00 P&L instead of actual P&L (e.g., ₹2,596.75).

## Root Cause
The `TradingBot` class initialized the Kite session once at startup. If the access token wasn't ready or was invalid at that moment, it got an unauthenticated session and never refreshed it, causing all P&L queries to return zero.

## Solution Applied

### 1. Lazy Session Initialization
- Bot no longer initializes Kite session in `__init__()`
- Session is initialized after handlers are set up
- Added `initialize_kite_session()` method

### 2. Session Validation
- Added `ensure_kite_session()` method
- Checks if session is valid before each API call
- Auto-reinitializes if session is invalid

### 3. Token Verification on Startup
- `start_bot_with_monitor.py` now waits 2 seconds after auto-login
- Verifies access token exists and is not empty
- Logs token prefix for debugging

### 4. Manual Reconnect Command
- Added `/reconnect` (alias: `/refresh`) command
- Manually reinitializes Kite session
- Shows P&L after reconnection to verify it works

## How to Apply the Fix

The fix is already applied to the code. To use it:

### Option 1: Restart Service
```bash
sudo systemctl restart kite-trading-bot
```

### Option 2: Test Logout Flow Again
```bash
# In Telegram
/logout

# Wait for service to auto-restart (about 10 seconds)

# Check status
/status

# If still showing zero, manually reconnect
/reconnect
```

## New Commands

### /reconnect (or /refresh)
Manually reinitializes the Kite session without restarting the bot.

```
/reconnect
```

Response shows:
- Day P&L
- Net P&L
- Open positions
- Confirmation that session is working

## Verification Steps

After restart, check:

1. **Service logs show token verification:**
```bash
sudo journalctl -u kite-trading-bot -f
```

Look for:
```
✅ Access token found: abcd1234...
✅ Kite session initialized for user: YOUR_NAME
```

2. **Telegram shows correct P&L:**
```
/status
```

Should show actual P&L, not ₹0.00

3. **If still zero, reconnect:**
```
/reconnect
```

## Troubleshooting

### Still Shows Zero After Reconnect

Check if access token is valid:
```bash
cat access_token.txt
```

Test manually:
```python
python -c "
from connect import get_kite_session
kite = get_kite_session()
print(kite.positions())
"
```

### "Session Invalid" Error

Token may have expired. Regenerate:
```bash
python auto_login.py
sudo systemctl restart kite-trading-bot
```

### Bot Starts But No P&L Data

Check Kite API status:
- Visit https://kite.zerodha.com/
- Check if you can login manually
- Verify API key is active

## Technical Details

### Before (Broken)
```python
class TradingBot:
    def __init__(self):
        self.kite = get_kite_session()  # ← Called once, never refreshed
```

If token was invalid at this moment, `self.kite` had no valid session.

### After (Fixed)
```python
class TradingBot:
    def __init__(self):
        self.kite = None
        # ... setup ...
        self.initialize_kite_session()  # ← Proper initialization
    
    def ensure_kite_session(self):
        """Check and refresh if needed"""
        if self.kite is None:
            return self.initialize_kite_session()
        try:
            self.kite.profile()  # ← Verify session
            return True
        except:
            return self.initialize_kite_session()  # ← Refresh if invalid
    
    def get_total_pnl(self):
        if not self.ensure_kite_session():  # ← Check before every call
            return 0, 0
        # ... fetch P&L ...
```

## Files Modified
- `telegram_bot.py` - Added session management methods
- `start_bot_with_monitor.py` - Added token verification on startup
- Added `/reconnect` command for manual session refresh

## Expected Behavior Now

✅ **After Logout + Restart:**
1. Auto-login generates token
2. Bot waits 2 seconds
3. Bot verifies token exists
4. Bot initializes Kite session
5. Session is validated with `profile()` call
6. P&L queries return actual data

✅ **If Session Becomes Invalid:**
1. Next P&L query detects invalid session
2. Auto-reinitializes session
3. Retries the query
4. Returns actual data

✅ **Manual Recovery:**
```
/reconnect → Forces session refresh → Shows P&L
```
