# TOTP Setup - Quick Guide

Your kill switch needs TOTP to automatically deactivate segments. Here's how to set it up:

## Step 1: Get Your TOTP Secret Key

### Option A: If you're setting up 2FA for the first time

1. Go to Zerodha Console: https://console.zerodha.com/
2. Navigate to: Settings → Security → Two-factor authentication
3. Click "Enable Two-factor authentication"
4. You'll see a QR code
5. Click "Can't scan? Enter this code manually"
6. **Copy the secret key** (looks like: `JBSWY3DPEHPK3PXP`)
7. Scan the QR code with your authenticator app
8. Verify it works

### Option B: If you already have 2FA enabled

You need to reset it:

1. Go to Zerodha Console
2. Settings → Security → Two-factor authentication
3. Click "Disable" (you'll need to enter current TOTP)
4. Then follow Option A above

## Step 2: Add to .env File

Edit your `.env` file and replace:
```
KITE_TOTP_KEY=your_totp_key_if_automating_login
```

With your actual key:
```
KITE_TOTP_KEY=JBSWY3DPEHPK3PXP
```

## Step 3: Test TOTP

Run this to test:
```bash
python test_totp.py
```

It should show a 6-digit code that matches your authenticator app.

## Step 4: Test Auto-Login

```bash
python auto_login.py
```

Should complete successfully and generate access token.

## Step 5: Test Segment Automation

```bash
python segment_automation.py
# Select option 3 (test login only)
```

## Security Notes

⚠️ **IMPORTANT:**
- Keep your TOTP key secret
- Never commit .env to git
- Anyone with this key can generate your 2FA codes
- Store it securely (password manager)

## Troubleshooting

**"TOTP key not configured"**
- Check .env file has the key
- Make sure it's not the placeholder text
- No spaces or quotes around the key

**"Invalid TOTP"**
- Check system time is correct
- TOTP is time-based
- Try generating a new key

**"Login failed"**
- Verify user ID and password are correct
- Check TOTP key is correct
- Test TOTP manually first

## What This Enables

Once configured, your system can:
- ✅ Auto-generate access tokens daily
- ✅ Auto-deactivate F&O segment on kill switch
- ✅ Fully automated trading (no manual intervention)

---

**Current Status:** ❌ TOTP Not Configured

Run `python test_totp.py` after adding your key to verify it works.
