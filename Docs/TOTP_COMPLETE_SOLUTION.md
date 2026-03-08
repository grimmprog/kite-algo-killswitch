# TOTP Complete Solution Guide

## Your Current Situation

✅ You have: `KITE_TOTP_KEY=L62UZQR2RNJNUKWONZPHMGSW7CZHGH22` in .env  
❌ Problem: pyotp not generating matching codes  
❌ Problem: Don't know how to use TOTP on other devices  
❌ Problem: Kill switch can't auto-deactivate segments  

## Quick Fix (5 Minutes)

### Step 1: Run Diagnostic

```bash
cd kite-algo
python diagnose_totp.py
```

**What it does:**
- Shows TOTP code from pyotp
- Asks you to compare with your phone app
- Identifies the exact problem

### Step 2: Follow the Fix

The diagnostic will tell you which issue you have:

**Issue A: Codes Match ✅**
- Your TOTP is working!
- Skip to "Using TOTP" section below

**Issue B: Codes Don't Match ❌**
- Most likely: System time is wrong
- Run: `python fix_totp_time_sync.py`
- This will sync your system time

**Issue C: Wrong TOTP Key ❌**
- You need to get the correct key from Zerodha
- Follow "Getting New TOTP Key" section below

---

## Getting New TOTP Key from Zerodha

If your current key doesn't work, get a new one:

### Step-by-Step:

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
   - Enter current TOTP from your app
   - Confirm

4. **Enable 2FA Again**
   - Click "Enable Two-factor authentication"
   - You'll see a QR code

5. **Get Secret Key**
   - Click: "Can't scan? Enter this code manually"
   - Copy the secret key (example: `L62UZQR2RNJNUKWONZPHMGSW7CZHGH22`)
   - **SAVE THIS KEY!**

6. **Scan QR Code**
   - Use your phone authenticator app
   - Scan the QR code
   - Verify it works

7. **Update .env File**
   ```env
   KITE_TOTP_KEY=L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
   ```

8. **Test Again**
   ```bash
   python diagnose_totp.py
   ```

---

## Using TOTP on Multiple Devices

**Good news:** Same key works on ALL devices!

### Add to Phone

**Google Authenticator:**
1. Open app → Tap "+"
2. Select "Enter a setup key"
3. Account: `Zerodha - YS2567`
4. Key: `L62UZQR2RNJNUKWONZPHMGSW7CZHGH22`
5. Type: Time-based
6. Tap "Add"

**Microsoft Authenticator:**
1. Open app → Tap "+"
2. Select "Other account"
3. Enter key manually
4. Done!

### Add to Computer

**Windows:**
- Install WinAuth: https://winauth.github.io/winauth/
- Add account with same key

**Mac:**
- Install Authy Desktop: https://authy.com/download/
- Add account with same key

**Linux:**
- Install OTPClient: `sudo apt install otpclient`
- Add account with same key

### Add to Python (Automation)

Already done! It's in your `.env` file:
```env
KITE_TOTP_KEY=L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
```

**All devices will show the SAME code at the SAME time!**

---

## Testing Everything

### Test 1: Basic TOTP

```bash
python test_totp.py
```

Shows 3 codes. Compare with your phone app.

### Test 2: Diagnostic (Recommended)

```bash
python diagnose_totp.py
```

Interactive test that asks you to verify codes match.

### Test 3: Time Sync (If Codes Don't Match)

```bash
python fix_totp_time_sync.py
```

Syncs your system time and tests again.

### Test 4: Auto-Login

```bash
python auto_login.py
```

Should complete successfully and generate access token.

### Test 5: Segment Automation

```bash
python segment_automation.py
# Select option 3 (test login only)
```

Should login to Zerodha Console successfully.

---

## Common Issues & Solutions

### Issue 1: "Codes don't match"

**Cause:** System time is wrong (TOTP is time-based)

**Solution:**
```bash
python fix_totp_time_sync.py
```

Or manually:
- **Windows:** Settings → Time & Language → Sync now
- **Linux:** `sudo ntpdate -s time.nist.gov`

### Issue 2: "Invalid TOTP key format"

**Cause:** Key has spaces, quotes, or wrong characters

**Solution:**
- Check .env file
- Key should be: `KITE_TOTP_KEY=L62UZQR2RNJNUKWONZPHMGSW7CZHGH22`
- No spaces, no quotes, no special characters

### Issue 3: "TOTP key not configured"

**Cause:** .env file not loaded or key is placeholder

**Solution:**
- Make sure .env file exists in kite-algo folder
- Check key is not: `your_totp_key_if_automating_login`
- Restart terminal after editing .env

### Issue 4: "Login failed" in segment automation

**Cause:** TOTP not working or credentials wrong

**Solution:**
1. Test TOTP first: `python diagnose_totp.py`
2. Verify credentials in .env:
   - `KITE_USER_ID=YS2567`
   - `KITE_PASSWORD=Aradhya@9900`
3. Try non-headless mode to see what's happening:
   ```python
   automation = ZerodhaSegmentAutomation(headless=False)
   ```

---

## What This Enables

Once TOTP is working:

### ✅ Automated Daily Login
```bash
python auto_login.py
```
- Runs at 9:15 AM automatically
- No manual intervention
- Access token generated

### ✅ Kill Switch Segment Deactivation
```bash
python advanced_killswitch.py
```
- Closes all positions
- Deactivates F&O segment automatically
- Prevents new trades

### ✅ Login from Any Device
- Use same TOTP key on all devices
- Phone, computer, automation - all work
- No need to reset 2FA

### ✅ Fully Automated Trading
- Bot runs 24/7
- No manual steps
- Complete automation

---

## Security Notes

⚠️ **IMPORTANT:**

1. **Keep TOTP key secret**
   - Anyone with this key can generate your 2FA codes
   - Treat it like a password

2. **Backup the key**
   - Save in password manager
   - Keep a secure backup
   - If you lose it, you'll need to reset 2FA

3. **Don't commit .env to git**
   - Already in .gitignore
   - Never share .env file

4. **Save backup codes**
   - Zerodha provides backup codes when setting up 2FA
   - Store them securely
   - Use if you lose TOTP access

---

## Quick Command Reference

```bash
# Test TOTP (basic)
python test_totp.py

# Test TOTP (interactive diagnostic)
python diagnose_totp.py

# Fix time sync issues
python fix_totp_time_sync.py

# Test auto-login
python auto_login.py

# Test segment automation
python segment_automation.py

# Test kill switch
python test_killswitch.py

# Generate TOTP manually
python -c "import pyotp; print(pyotp.TOTP('L62UZQR2RNJNUKWONZPHMGSW7CZHGH22').now())"
```

---

## Troubleshooting Flowchart

```
Start
  ↓
Run: python diagnose_totp.py
  ↓
Codes match? ──YES──→ ✅ Done! Test auto-login
  ↓
 NO
  ↓
Run: python fix_totp_time_sync.py
  ↓
Codes match now? ──YES──→ ✅ Done! Test auto-login
  ↓
 NO
  ↓
Check .env file:
- Key correct?
- No spaces/quotes?
  ↓
Still not working? ──→ Reset 2FA on Zerodha
  ↓
Get new secret key
  ↓
Update .env
  ↓
Run: python diagnose_totp.py
  ↓
✅ Done!
```

---

## Next Steps

1. **Run diagnostic:**
   ```bash
   python diagnose_totp.py
   ```

2. **If codes match:**
   - Test auto-login: `python auto_login.py`
   - Test segment automation: `python segment_automation.py`
   - Enable kill switch: Ready to use!

3. **If codes don't match:**
   - Fix time: `python fix_totp_time_sync.py`
   - Or reset 2FA and get new key

4. **Add to other devices:**
   - Use same key: `L62UZQR2RNJNUKWONZPHMGSW7CZHGH22`
   - All devices will generate matching codes

---

## Files Created

- ✅ `diagnose_totp.py` - Interactive TOTP diagnostic
- ✅ `fix_totp_time_sync.py` - Fix time synchronization
- ✅ `TOTP_MULTI_DEVICE_GUIDE.md` - Detailed multi-device guide
- ✅ `TOTP_COMPLETE_SOLUTION.md` - This file (quick reference)
- ✅ Updated `test_totp.py` - Basic TOTP test

---

## Support

Still having issues? Check:

1. **System time is correct**
   - TOTP is time-based
   - Even 1 minute off will cause issues

2. **Key format is correct**
   - Base32 encoded (A-Z, 2-7)
   - No spaces, quotes, or special characters

3. **Using correct key**
   - Same key as in your authenticator app
   - If unsure, reset 2FA and get new key

4. **Credentials are correct**
   - User ID: YS2567
   - Password: (check .env)
   - TOTP key: (check .env)

---

**Ready to start?**

```bash
python diagnose_totp.py
```

This will identify and help fix your specific issue!
