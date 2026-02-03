# Google Authenticator + Python - Quick Fix

## The Problem

Google Authenticator shows one code, Python shows different code.

## Why?

Google Authenticator **hides** the secret key. You can't extract it.

## The Fix (5 Minutes)

### Step 1: Reset 2FA on Zerodha

```
1. Go to: https://console.zerodha.com/
2. Settings → Security → Two-factor authentication
3. Click "Disable" (enter current code)
4. Click "Enable" again
```

### Step 2: Get Secret Key

```
5. You'll see a QR code
6. Click: "Can't scan? Enter this code manually"
7. Copy the key: L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
   ⚠️ SAVE THIS KEY!
```

### Step 3: Add to Google Authenticator

```
8. Open Google Authenticator
9. Tap "+" → "Enter a setup key" (NOT scan QR!)
10. Account: Zerodha - YS2567
11. Key: L62UZQR2RNJNUKWONZPHMGSW7CZHGH22 (paste)
12. Type: Time based
13. Tap "Add"
14. Enter code on Zerodha to verify
```

### Step 4: Add to Python

```
15. Open: kite-algo/.env
16. Update: KITE_TOTP_KEY=L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
    (same key as Google Authenticator!)
17. Save file
```

### Step 5: Test

```bash
python diagnose_totp.py
```

Compare code with Google Authenticator - should match!

---

## Visual Guide

```
┌─────────────────────────────────────────┐
│  Zerodha 2FA Setup                      │
│  Secret: L62UZQR2RNJNUKWONZPHMGSW7CZHGH22│
└────────────┬────────────────────────────┘
             │
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
┌─────────┐      ┌─────────┐
│ Google  │      │ Python  │
│  Auth   │      │  .env   │
├─────────┤      ├─────────┤
│ Key:    │      │ Key:    │
│ L62UZ...│      │ L62UZ...│
├─────────┤      ├─────────┤
│ Code:   │      │ Code:   │
│ 123456  │      │ 123456  │
└─────────┘      └─────────┘
    ✅ MATCH!
```

---

## Key Points

✅ **MUST reset 2FA** - Can't extract key from Google Authenticator  
✅ **Get key during setup** - Click "Enter this code manually"  
✅ **Use SAME key** - Both Google Auth and Python  
✅ **Enter key manually** - Don't just scan QR code  
✅ **Test immediately** - Run `python diagnose_totp.py`  

---

## Common Mistakes

❌ **Scanning QR code only** - You won't have the key for Python  
❌ **Different keys** - Google Auth and Python must use same key  
❌ **Typos in .env** - No spaces, no quotes  
❌ **Wrong time** - Run `python fix_totp_time_sync.py`  

---

## If Codes Still Don't Match

```bash
# Fix time sync (most common issue)
python fix_totp_time_sync.py

# Full diagnostic
python diagnose_totp.py

# Check .env format
# Should be: KITE_TOTP_KEY=L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
# No spaces, no quotes!
```

---

## Your Current Setup

```
User: YS2567
Key in .env: L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
```

**To sync Google Authenticator:**

**Option 1: Use existing key**
1. Delete Zerodha from Google Authenticator
2. Add new entry with key from .env
3. Test: `python diagnose_totp.py`

**Option 2: Reset and start fresh (recommended)**
1. Follow steps above
2. Get new key
3. Add to both Google Auth and .env
4. Test: `python diagnose_totp.py`

---

## What This Enables

✅ Kill switch auto-deactivation  
✅ Daily auto-login (9:15 AM)  
✅ Fully automated trading  
✅ Manual login backup (Google Auth)  

---

## Need More Help?

**Read these guides:**
- `SYNC_GOOGLE_AUTHENTICATOR.md` - Detailed Google Auth guide
- `TOTP_COMPLETE_SOLUTION.md` - Complete troubleshooting
- `GOOGLE_AUTHENTICATOR_SYNC.md` - Alternative methods

**Run these commands:**
```bash
python diagnose_totp.py          # Find the problem
python fix_totp_time_sync.py     # Fix time issues
python setup_totp_wizard.py      # Interactive setup
```

---

**Ready?**

Start with Step 1: Reset 2FA on Zerodha Console!

The whole process takes 5 minutes and you'll have both synced! 🚀
