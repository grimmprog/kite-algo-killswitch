# Historical Data API - Important Note

## Issue: "Insufficient permission for that call"

This error occurs because your Kite Connect app doesn't have **historical data permission enabled**.

### Good News: It's FREE! ✅

Historical data API is **included** with Kite Connect at no extra cost. You just need to enable the permission.

## Quick Fix (5 minutes):

1. **Go to:** https://developers.kite.trade/
2. **Login** with Zerodha credentials
3. **Click** "My Apps"
4. **Edit** your app
5. **Enable** "Historical data" permission
6. **Save** changes
7. **Wait** 10 minutes
8. **Generate new token:** `python login.py`
9. **Test:** `python main.py`

**Detailed guide:** See `FIX_HISTORICAL_DATA.md`

---

## What This Enables:

Once fixed, your bot will have:

- ✅ Automated strategy scanning
- ✅ Technical indicator calculations  
- ✅ NIFTY & BANKNIFTY monitoring
- ✅ Trade signal generation
- ✅ Full automation

## Current Bot Capabilities:

| Feature | Status |
|---------|--------|
| Manual order placement | ✅ Working |
| Position monitoring | ✅ Working |
| Kill switch | ✅ Working |
| Segment automation | ⚠️ Needs TOTP |
| Telegram control | ✅ Working |
| P&L tracking | ✅ Working |
| Risk management | ✅ Working |
| **Automated scanning** | ⚠️ Needs permission |
| **Strategy signals** | ⚠️ Needs permission |

## Summary:

**Issue:** Historical data permission not enabled in Kite app

**Cost:** FREE (included with Kite Connect)

**Fix Time:** 15 minutes (5 min setup + 10 min propagation)

**Fix Guide:** `FIX_HISTORICAL_DATA.md`

---

**After fixing, your bot will be fully automated!** 🚀
