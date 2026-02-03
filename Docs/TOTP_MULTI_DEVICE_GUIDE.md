# TOTP Multi-Device Setup Guide

## Problem You're Facing

You have TOTP set up on your authenticator app, but:
1. ❌ pyotp is not generating matching codes for automation
2. ❌ You don't know how to use TOTP on other devices (phone, computer, etc.)
3. ❌ Kill switch can't auto-deactivate segments without working TOTP

## Solution Overview

The same TOTP secret key can be used on:
- ✅ Your phone authenticator app
- ✅ Your computer authenticator app
- ✅ Python automation (pyotp)
- ✅ Multiple devices simultaneously

**Key insight:** All devices use the SAME secret key to generate codes.

---

## Step 1: Get Your TOTP Secret Key

### Option A: If You Have the Secret Key Already

If you saved the secret key when setting up 2FA, skip to Step 2.

### Option B: Extract from Zerodha (Recommended)

Since you can't extract the key from most authenticator apps, you need to reset 2FA:

1. **Login to Zerodha Console**
   - Go to: https://console.zerodha.com/
   - Login with your credentials

2. **Navigate to 2FA Settings**
   - Click: Settings → Security → Two-factor authentication

3. **Disable Current 2FA**
   - Click "Disable" button
   - Enter current TOTP code from your app
   - Confirm disable

4. **Re-enable 2FA**
   - Click "Enable Two-factor authentication"
   - You'll see a QR code screen

5. **Get the Secret Key**
   - Look for: "Can't scan? Enter this code manually"
   - Click it to reveal the secret key
   - Example: `L62UZQR2RNJNUKWONZPHMGSW7CZHGH22`
   - **COPY THIS KEY IMMEDIATELY!**

6. **Save It Securely**
   - Save in password manager
   - Save in `.env` file
   - Keep a backup somewhere safe

---

## Step 2: Add TOTP to All Your Devices

Now that you have the secret key, add it to all devices:

### A. Phone Authenticator App

**Google Authenticator:**
1. Open Google Authenticator
2. Tap "+" → "Enter a setup key"
3. Account name: `Zerodha - YS2567`
4. Key: `L62UZQR2RNJNUKWONZPHMGSW7CZHGH22`
5. Type: Time-based
6. Tap "Add"

**Microsoft Authenticator:**
1. Open Microsoft Authenticator
2. Tap "+" → "Other account"
3. Scan QR code OR enter key manually
4. If manual: Enter the secret key
5. Done!

**Authy:**
1. Open Authy
2. Tap "+" → "Add Account"
3. Scan QR code OR enter key manually
4. Name: `Zerodha - YS2567`
5. Done!

### B. Computer Authenticator App

**Windows/Mac/Linux:**

Install an authenticator app:
- **Authy Desktop**: https://authy.com/download/
- **WinAuth** (Windows): https://winauth.github.io/winauth/
- **OTPClient** (Linux): Available in package managers

Then add the same secret key as above.

### C. Python Automation (pyotp)

1. **Update .env file:**
   ```env
   KITE_TOTP_KEY=L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
   ```

2. **Test it:**
   ```bash
   python diagnose_totp.py
   ```

3. **Verify codes match:**
   - The script will show a code
   - Compare with your phone app
   - They should be IDENTICAL

---

## Step 3: Verify Everything Works

### Test 1: Compare Codes Across Devices

Run this test:

```bash
python diagnose_totp.py
```

**What it does:**
1. Shows current TOTP code from pyotp
2. Asks you to enter code from your phone app
3. Compares them
4. If they match → ✅ Success!
5. If they don't match → ❌ See troubleshooting below

### Test 2: Test Auto-Login

```bash
python auto_login.py
```

Should complete successfully without errors.

### Test 3: Test Segment Automation

```bash
python segment_automation.py
# Select option 3 (test login only)
```

Should login successfully.

---

## Troubleshooting

### Issue 1: Codes Don't Match

**Possible causes:**

1. **Wrong secret key in .env**
   - Solution: Double-check the key
   - Make sure no spaces or quotes
   - Should be exactly as shown in Zerodha

2. **System time is wrong**
   - TOTP is time-based
   - If your computer time is off by even 1 minute, codes won't match
   - Solution: Sync your system time
   
   **Windows:**
   ```powershell
   w32tm /resync
   ```
   
   **Linux:**
   ```bash
   sudo ntpdate -s time.nist.gov
   ```

3. **Key format issue**
   - TOTP keys are base32 encoded
   - Valid characters: A-Z, 2-7
   - Invalid: 0, 1, 8, 9, lowercase letters
   - Solution: Get a fresh key from Zerodha

### Issue 2: "Invalid TOTP" During Login

**Causes:**
- Code expired (codes change every 30 seconds)
- System time drift
- Wrong key

**Solutions:**
1. Run `diagnose_totp.py` to verify codes match
2. Check system time is correct
3. Try generating a new key from Zerodha

### Issue 3: Can't Login on Other Devices

**If you want to login manually on another device:**

1. **Option A: Use authenticator app**
   - Add the same TOTP key to that device's authenticator app
   - Use the generated code to login

2. **Option B: Use backup codes**
   - Zerodha provides backup codes when setting up 2FA
   - Use those if you don't have the TOTP key

---

## How TOTP Works (Technical)

Understanding this helps troubleshoot:

1. **Secret Key**: `L62UZQR2RNJNUKWONZPHMGSW7CZHGH22`
   - This is the "seed" that generates codes
   - Same key = same codes
   - Keep it secret!

2. **Time-Based**: 
   - Uses current time to generate codes
   - Codes change every 30 seconds
   - All devices must have correct time

3. **Algorithm**:
   ```
   Code = TOTP(secret_key, current_time)
   ```
   - Same key + same time = same code
   - Works on any device

4. **Why it's secure**:
   - Even if someone sees your code, it expires in 30s
   - They still need your password
   - Secret key never transmitted

---

## Using TOTP on Multiple Devices Simultaneously

**Good news:** You can use the same TOTP key on unlimited devices!

**Example setup:**
- 📱 Phone: Google Authenticator with key
- 💻 Computer: Authy Desktop with same key
- 🤖 Bot: pyotp with same key in .env
- 📱 Backup phone: Microsoft Authenticator with same key

**All will generate the SAME code at the SAME time!**

---

## Security Best Practices

1. **Backup the secret key**
   - Save in password manager (1Password, Bitwarden, etc.)
   - Don't lose it!

2. **Save backup codes**
   - Zerodha provides backup codes
   - Store them securely
   - Use if you lose TOTP access

3. **Don't share the key**
   - Anyone with the key can generate your codes
   - Treat it like a password

4. **Keep .env secure**
   - Never commit to git
   - Use .gitignore
   - Restrict file permissions

---

## Quick Reference

### Generate TOTP code manually:

```bash
python -c "import pyotp; print(pyotp.TOTP('YOUR_KEY').now())"
```

### Test TOTP:

```bash
python diagnose_totp.py
```

### Your current key:

```
L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
```

### Add to new device:

1. Open authenticator app
2. Add account manually
3. Enter key: `L62UZQR2RNJNUKWONZPHMGSW7CZHGH22`
4. Type: Time-based
5. Done!

---

## What This Enables

Once TOTP is working:

✅ **Automated daily login** (9:15 AM)
- No manual intervention needed
- Access token generated automatically

✅ **Kill switch segment deactivation**
- Automatically disables F&O segment
- Prevents new trades after loss limit

✅ **Login from any device**
- Use same TOTP key on all devices
- No need to reset 2FA

✅ **Fully automated trading**
- Bot can run 24/7
- No manual steps required

---

## Next Steps

1. **Run diagnostic:**
   ```bash
   python diagnose_totp.py
   ```

2. **If codes match:**
   - ✅ You're done!
   - Test auto-login and segment automation

3. **If codes don't match:**
   - Reset 2FA on Zerodha
   - Get new secret key
   - Update .env file
   - Run diagnostic again

4. **Add to other devices:**
   - Use the same secret key
   - All devices will generate matching codes

---

## Support

If you're still having issues:

1. Check system time is correct
2. Verify key has no spaces/quotes in .env
3. Try resetting 2FA and getting a fresh key
4. Run `diagnose_totp.py` for detailed diagnostics

**Remember:** The secret key is the ONLY thing you need. Once you have it, you can use it on unlimited devices!
