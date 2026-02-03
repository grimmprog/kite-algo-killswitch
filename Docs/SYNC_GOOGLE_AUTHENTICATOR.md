# How to Sync Google Authenticator with Python

## TL;DR

**You can't extract the key from Google Authenticator.**

**Solution:** Reset 2FA on Zerodha, get the secret key, add it to BOTH Google Authenticator and Python.

---

## The Problem

```
┌─────────────────────┐         ┌─────────────────────┐
│ Google Authenticator│         │   Python (pyotp)    │
│                     │         │                     │
│   Code: 123456      │   ❌    │   Code: 789012      │
│                     │         │                     │
└─────────────────────┘         └─────────────────────┘
        DON'T MATCH!
```

**Why?** They're using different secret keys.

---

## The Solution

```
                    ┌──────────────────────────┐
                    │   Zerodha 2FA Setup      │
                    │  Secret Key: ABC123XYZ   │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────┴─────────────┐
                    │                          │
         ┌──────────▼──────────┐    ┌─────────▼──────────┐
         │ Google Authenticator│    │  Python (.env)     │
         │                     │    │                    │
         │  Key: ABC123XYZ     │    │ Key: ABC123XYZ     │
         │  Code: 123456       │    │ Code: 123456       │
         └─────────────────────┘    └────────────────────┘
                    ✅ MATCH!
```

**Both use the SAME secret key = SAME codes!**

---

## Step-by-Step Guide

### Step 1: Reset 2FA on Zerodha (5 minutes)

1. **Go to Zerodha Console**
   ```
   https://console.zerodha.com/
   ```

2. **Navigate to 2FA**
   ```
   Settings → Security → Two-factor authentication
   ```

3. **Disable Current 2FA**
   - Click "Disable"
   - Enter current code from Google Authenticator
   - Confirm

4. **Enable 2FA Again**
   - Click "Enable Two-factor authentication"
   - You'll see a QR code

5. **Get the Secret Key** ⭐ IMPORTANT!
   - Click: "Can't scan? Enter this code manually"
   - You'll see something like: `L62UZQR2RNJNUKWONZPHMGSW7CZHGH22`
   - **COPY THIS KEY!** You need it for both apps

---

### Step 2: Add to Google Authenticator

6. **Open Google Authenticator on Your Phone**

7. **Add Account**
   - Tap "+" (bottom right)
   - Select "Enter a setup key" (NOT scan QR code!)

8. **Enter Details**
   ```
   Account name: Zerodha - YS2567
   Your key: L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
   Type of key: Time based
   ```

9. **Tap "Add"**
   - Google Authenticator will start showing codes
   - Example: `123456`

10. **Verify on Zerodha**
    - Enter the code from Google Authenticator
    - Complete 2FA setup
    - ✅ Google Authenticator is now working!

---

### Step 3: Add to Python

11. **Open .env File**
    ```
    kite-algo/.env
    ```

12. **Update TOTP Key**
    ```env
    KITE_TOTP_KEY=L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
    ```
    ⚠️ Use the SAME key you added to Google Authenticator!
    ⚠️ No spaces, no quotes, no special characters

13. **Save the File**

---

### Step 4: Test Everything

14. **Run Diagnostic**
    ```bash
    cd kite-algo
    python diagnose_totp.py
    ```

15. **Compare Codes**
    - Script shows: `Current TOTP: 123456`
    - Check Google Authenticator: Should also show `123456`
    - Script asks: "Enter code from your app"
    - Type the code from Google Authenticator
    - Result: ✅ "CODES MATCH!"

16. **Test Auto-Login**
    ```bash
    python auto_login.py
    ```
    Should complete successfully!

---

## Visual Walkthrough

### Before (Not Synced)

```
Zerodha 2FA Setup (Old)
    ↓
Google Authenticator          Python
Secret: ???                   Secret: L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
Code: 123456                  Code: 789012
    ❌ DON'T MATCH ❌
```

### After (Synced)

```
Zerodha 2FA Setup (New)
Secret: L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
    ↓                              ↓
Google Authenticator          Python (.env)
Secret: L62UZQR2RNJNUKWONZPHMGSW7CZHGH22    Secret: L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
Code: 123456                  Code: 123456
    ✅ MATCH! ✅
```

---

## Common Mistakes

### ❌ Mistake 1: Scanning QR Code

**Wrong:**
- Scan QR code with Google Authenticator
- Don't save the secret key
- Can't add to Python

**Right:**
- Click "Enter this code manually"
- Copy the secret key
- Add to both Google Authenticator AND Python

### ❌ Mistake 2: Different Keys

**Wrong:**
```env
# Google Authenticator has: ABC123
# Python .env has: XYZ789
# Codes won't match!
```

**Right:**
```env
# Both have: L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
# Codes will match!
```

### ❌ Mistake 3: Typos in .env

**Wrong:**
```env
KITE_TOTP_KEY = "L62UZQR2RNJNUKWONZPHMGSW7CZHGH22"  # Has quotes and spaces
KITE_TOTP_KEY=L62UZQR2 RNJNUKWONZPHMGSW7CZHGH22     # Has space in middle
```

**Right:**
```env
KITE_TOTP_KEY=L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
```

---

## Troubleshooting

### Codes Still Don't Match?

**Check 1: System Time**
```bash
python fix_totp_time_sync.py
```
TOTP is time-based. If your computer time is wrong, codes won't match.

**Check 2: Same Key?**
- Open .env file
- Check Google Authenticator (you can't see the key, but you added it)
- Make sure you used the same key for both

**Check 3: Key Format**
- No spaces
- No quotes
- All uppercase
- Only A-Z and 2-7

**Still not working?**
- Try resetting 2FA again
- Make sure to copy the key correctly
- Test immediately after setup

---

## Why This is Necessary

**Google Authenticator doesn't let you:**
- ❌ See the secret key after setup
- ❌ Export accounts
- ❌ Backup to cloud
- ❌ Sync across devices

**So you MUST:**
- ✅ Get the key during initial setup
- ✅ Save it somewhere (password manager)
- ✅ Use same key for all devices

---

## Alternative: Better Authenticator Apps

If you want easier syncing, consider:

### Microsoft Authenticator
- ✅ Shows secret key
- ✅ Cloud backup
- ✅ Multi-device sync

### Authy
- ✅ Desktop app
- ✅ Cloud backup
- ✅ Multi-device sync

### How to Switch:
1. Get your key: `L62UZQR2RNJNUKWONZPHMGSW7CZHGH22`
2. Install new authenticator app
3. Add account with same key
4. Keep Google Authenticator as backup
5. All will show same codes!

---

## Quick Commands

```bash
# Test if codes match
python diagnose_totp.py

# Fix time sync issues
python fix_totp_time_sync.py

# Test auto-login
python auto_login.py

# Test segment automation
python segment_automation.py
```

---

## Summary

**The key to syncing:**
1. Reset 2FA on Zerodha
2. Get the secret key (click "Enter this code manually")
3. Add to Google Authenticator (enter key manually, not QR scan)
4. Add to Python .env file (same key!)
5. Test with `python diagnose_totp.py`

**Result:** Both will show the same code! ✅

---

## Your Current Key

From your .env file:
```
KITE_TOTP_KEY=L62UZQR2RNJNUKWONZPHMGSW7CZHGH22
```

**To sync Google Authenticator:**
1. Delete old Zerodha entry in Google Authenticator
2. Add new entry with key: `L62UZQR2RNJNUKWONZPHMGSW7CZHGH22`
3. Test: `python diagnose_totp.py`

**OR (recommended):**
1. Reset 2FA on Zerodha
2. Get fresh key
3. Add to both Google Authenticator and .env
4. Test: `python diagnose_totp.py`

---

**Ready to sync?**

Follow the steps above, and you'll have Google Authenticator and Python showing the same codes in 5 minutes! 🚀
