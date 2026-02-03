# Google Authenticator Sync Guide

## The Problem

You have Google Authenticator on your phone showing TOTP codes, but pyotp (Python automation) is not generating matching codes.

## Why This Happens

Google Authenticator **hides the secret key** after initial setup. You can't extract it from the app. This means:

❌ Can't get the key from Google Authenticator  
❌ Can't sync existing Google Authenticator with Python  
✅ **Solution:** Need to reset 2FA and set up both at the same time  

---

## The Solution (2 Options)

### Option 1: Reset 2FA and Set Up Both Together (Recommended)

This is the ONLY way to sync Google Authenticator with Python automation.

#### Step 1: Reset 2FA on Zerodha

1. **Login to Zerodha Console**
   ```
   https://console.zerodha.com/
   ```

2. **Go to 2FA Settings**
   ```
   Settings → Security → Two-factor authentication
   ```

3. **Disable Current 2FA**
   - Click "Disable"
   - Enter current TOTP from Google Authenticator
   - Confirm disable

4. **Enable 2FA Again**
   - Click "Enable Two-factor authentication"
   - You'll see a QR code screen

#### Step 2: Get the Secret Key

5. **Extract Secret Key**
   - Look for: "Can't scan? Enter this code manually"
   - Click it to reveal the secret key
   - Example: `L62UZQR2RNJNUKWONZPHMGSW7CZHGH22`
   - **COPY THIS KEY!** (You'll need it for both)

#### Step 3: Add to Google Authenticator

6. **On Your Phone:**
   - Open Google Authenticator
   - Tap "+" (Add account)
   - Select "Enter a setup key" (NOT scan QR code)
   - Account name: `Zerodha - YS2567`
   - Your key: `L62UZQR2RNJNUKWONZPHMGSW7CZHGH22` (paste the key you copied)
   - Type of key: Time based
   - Tap "Add"

7. **Verify It Works**
   - Google Authenticator will show a 6-digit code
   - Enter it on Zerodha to complete 2FA setup
   - ✅ Google Authenticator is now set up!

#### Step 4: Add to Python (.env file)

8. **Update .env File**
   ```env
   KITE_TOTP_KEY=L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
   ```
   (Use the SAME key you added to Google Authenticator)

9. **Test Python TOTP**
   ```bash
   python diagnose_totp.py
   ```

10. **Compare Codes**
    - The script will show a code
    - Check Google Authenticator on your phone
    - **They should be IDENTICAL!**

---

### Option 2: Use Your Existing Key (If You Have It)

If you already have the secret key in your `.env` file and it's correct:

#### Step 1: Remove Old Google Authenticator Entry

1. Open Google Authenticator
2. Find your Zerodha entry
3. Long press → Delete

#### Step 2: Add Using Your .env Key

1. Open your `.env` file
2. Copy the TOTP key: `L62UZQR2RNJNUKWONZPHMGSW7CZHGH22`

3. In Google Authenticator:
   - Tap "+"
   - Select "Enter a setup key"
   - Account: `Zerodha - YS2567`
   - Key: `L62UZQR2RNJNUKWONZPHMGSW7CZHGH22` (from .env)
   - Type: Time based
   - Tap "Add"

4. **Test:**
   ```bash
   python diagnose_totp.py
   ```
   
   Compare the code with Google Authenticator - they should match!

---

## Why Google Authenticator is Different

**Google Authenticator limitations:**
- ❌ Doesn't show the secret key after setup
- ❌ Can't export accounts
- ❌ Can't backup to cloud
- ❌ Can't sync across devices easily

**Better alternatives:**
- ✅ **Microsoft Authenticator** - Cloud backup, shows key
- ✅ **Authy** - Multi-device sync, cloud backup
- ✅ **Aegis** (Android) - Open source, export/import

But if you prefer Google Authenticator, the reset method above works perfectly!

---

## Step-by-Step Visual Guide

### Current Situation:
```
Google Authenticator (Phone)     Python (Computer)
        ↓                              ↓
    Shows: 123456                 Shows: 789012
        ❌ DON'T MATCH ❌
```

### After Syncing:
```
        Secret Key: L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
                    ↓                    ↓
    Google Authenticator          Python (.env)
            ↓                           ↓
        Shows: 123456              Shows: 123456
            ✅ MATCH! ✅
```

---

## Testing After Setup

### Test 1: Visual Comparison

```bash
python diagnose_totp.py
```

**What happens:**
1. Script shows: `Current TOTP: 123456`
2. Check Google Authenticator: Should also show `123456`
3. Script asks: "Enter code from your app"
4. Type: `123456`
5. Result: ✅ "CODES MATCH!"

### Test 2: Auto-Login

```bash
python auto_login.py
```

Should complete successfully without errors.

### Test 3: Segment Automation

```bash
python segment_automation.py
# Select option 3 (test login only)
```

Should login to Zerodha successfully.

---

## Troubleshooting

### Issue 1: Codes Still Don't Match

**Possible causes:**

1. **System time is wrong**
   - TOTP is time-based
   - Even 1 minute off = codes won't match
   
   **Fix:**
   ```bash
   python fix_totp_time_sync.py
   ```

2. **Different keys**
   - Google Authenticator has old key
   - Python has different key
   
   **Fix:** Reset 2FA and set up both with same key (Option 1 above)

3. **Typo in .env file**
   - Check for spaces, quotes, or wrong characters
   
   **Fix:** 
   ```env
   # Wrong:
   KITE_TOTP_KEY = "L62UZQR2RNJNUKWONZPHMGSW7CZHGH22"
   
   # Correct:
   KITE_TOTP_KEY=L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
   ```

### Issue 2: "Can't Extract Key from Google Authenticator"

**This is normal!** Google Authenticator doesn't allow key extraction.

**Solution:** Reset 2FA on Zerodha and set up both together (Option 1)

### Issue 3: Codes Match But Login Fails

**Possible causes:**
- Code expired (codes change every 30 seconds)
- Network issue
- Wrong credentials

**Fix:**
1. Check user ID and password in .env
2. Try again with fresh code
3. Run in non-headless mode to see what's happening

---

## Quick Reference

### Your Current Setup:
```
User ID: YS2567
TOTP Key: L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
```

### To Sync Google Authenticator:

**Method 1: Reset 2FA (Recommended)**
1. Disable 2FA on Zerodha
2. Enable 2FA again
3. Get secret key
4. Add to Google Authenticator (enter key manually)
5. Add to .env file (same key)
6. Test: `python diagnose_totp.py`

**Method 2: Use Existing Key**
1. Get key from .env: `L62UZQR2RNJNUKWONZPHMGSW7CZHGH22`
2. Delete old entry in Google Authenticator
3. Add new entry with this key
4. Test: `python diagnose_totp.py`

---

## Important Notes

### ⚠️ Before You Start

1. **Save backup codes** from Zerodha (when resetting 2FA)
2. **Keep the secret key safe** (password manager)
3. **Test immediately** after setup

### ✅ After Setup

1. **Both will show same code** at same time
2. **Code changes every 30 seconds** (normal)
3. **All devices can use same key** (unlimited)

### 🔒 Security

1. **Never share the secret key**
2. **Don't commit .env to git** (already in .gitignore)
3. **Keep backup codes secure**

---

## What This Enables

Once Google Authenticator and Python are synced:

✅ **Kill Switch Auto-Deactivation**
```bash
python advanced_killswitch.py
```
- Automatically disables F&O segment
- No manual intervention needed

✅ **Daily Auto-Login (9:15 AM)**
```bash
python auto_login.py
```
- Generates access token automatically
- No manual steps required

✅ **Manual Login Backup**
- If automation fails, use Google Authenticator
- Same code works for both

---

## Alternative: Switch to Better Authenticator

If you want easier multi-device sync, consider:

### Microsoft Authenticator
- ✅ Cloud backup
- ✅ Shows secret key
- ✅ Multi-device sync
- ✅ Free

### Authy
- ✅ Multi-device sync
- ✅ Cloud backup
- ✅ Desktop app available
- ✅ Free

### Setup with Alternative:
1. Install new authenticator app
2. Use same key: `L62UZQR2RNJNUKWONZPHMGSW7CZHGH22`
3. Keep Google Authenticator as backup
4. All will show same codes!

---

## Summary

**The key insight:** Google Authenticator and Python need the **SAME secret key**.

**How to get it:**
1. Reset 2FA on Zerodha
2. Get the secret key when setting up
3. Add to both Google Authenticator AND .env file
4. Test with `python diagnose_totp.py`

**Result:** Both will generate identical codes! ✅

---

## Next Steps

1. **Decide which option:**
   - Option 1: Reset 2FA (recommended, guaranteed to work)
   - Option 2: Use existing key (if you have it)

2. **Follow the steps above**

3. **Test:**
   ```bash
   python diagnose_totp.py
   ```

4. **If codes match:**
   - ✅ You're done!
   - Test auto-login: `python auto_login.py`

5. **If codes don't match:**
   - Run: `python fix_totp_time_sync.py`
   - Or try Option 1 (reset 2FA)

---

**Ready to sync?**

Start with Option 1 (reset 2FA) - it's the most reliable way to ensure both Google Authenticator and Python have the exact same key!
