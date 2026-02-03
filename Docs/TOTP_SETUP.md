# TOTP Setup Guide for Automated Segment Control

To enable automatic segment deactivation, you need to configure your TOTP (Time-based One-Time Password) key.

## What is TOTP?

TOTP is the 6-digit code you enter for 2-factor authentication when logging into Zerodha. To automate this, we need the secret key that generates these codes.

## How to Get Your TOTP Key

### Method 1: From Existing Authenticator App

If you already have 2FA set up with an authenticator app (Google Authenticator, Authy, etc.):

1. **Google Authenticator:**
   - Unfortunately, Google Authenticator doesn't show the secret key
   - You'll need to reset 2FA and use Method 2

2. **Authy:**
   - Authy also doesn't expose the secret key
   - You'll need to reset 2FA and use Method 2

3. **Other Apps (Microsoft Authenticator, etc.):**
   - Check if your app has an "Export" or "Show Secret" option
   - If not, use Method 2

### Method 2: Reset and Reconfigure 2FA (Recommended)

1. **Login to Zerodha Console:**
   - Go to: https://console.zerodha.com/
   - Navigate to: Settings → Security → Two-factor authentication

2. **Disable Current 2FA:**
   - Click "Disable" on your current 2FA
   - Confirm the action

3. **Re-enable 2FA:**
   - Click "Enable Two-factor authentication"
   - You'll see a QR code

4. **Extract the Secret Key:**
   - Look for a link that says "Can't scan? Enter this code manually"
   - Click it to reveal the secret key
   - It will look like: `JBSWY3DPEHPK3PXP` (16-32 characters)
   - **IMPORTANT:** Copy this key immediately!

5. **Scan QR Code:**
   - Use your authenticator app to scan the QR code
   - Or manually enter the secret key you just copied
   - Verify it works by entering the 6-digit code

6. **Save the Secret Key:**
   - Add it to your `.env` file:
     ```
     KITE_TOTP_KEY=JBSWY3DPEHPK3PXP
     ```

## Security Notes

⚠️ **IMPORTANT SECURITY WARNINGS:**

1. **Keep Secret Key Safe:**
   - The TOTP key is as sensitive as your password
   - Anyone with this key can generate your 2FA codes
   - Never share it or commit it to public repositories

2. **Backup:**
   - Save the key in a secure password manager
   - If you lose it, you'll need to reset 2FA again

3. **Multiple Devices:**
   - You can use the same TOTP key on multiple devices
   - Add it to both your phone authenticator AND the bot

## Testing TOTP

Test if your TOTP key works:

```bash
python -c "import pyotp; print(pyotp.TOTP('YOUR_KEY_HERE').now())"
```

This should print a 6-digit code that matches your authenticator app.

## Configuration

Update your `.env` file:

```env
# Kite Connect Credentials
KITE_API_KEY=your_api_key
KITE_API_SECRET=your_api_secret
KITE_USER_ID=YS2567
KITE_PASSWORD=your_password
KITE_TOTP_KEY=JBSWY3DPEHPK3PXP  # ← Add this line
```

## Test Segment Automation

Once configured, test the automation:

```bash
python segment_automation.py
```

Select option 3 to test login only (no changes).

## Troubleshooting

### "TOTP key not configured" Error
- Make sure `KITE_TOTP_KEY` is set in `.env`
- Verify it's not set to `your_totp_key_if_automating_login`

### "Invalid TOTP" Error
- Check if the key is correct
- Ensure your system time is synchronized
- TOTP codes are time-based and require accurate system time

### Login Fails
- Verify `KITE_USER_ID` and `KITE_PASSWORD` are correct
- Check if Zerodha has changed their login page structure
- Try running in non-headless mode to see what's happening:
  ```python
  automation = ZerodhaSegmentAutomation(headless=False)
  ```

## Alternative: Manual Segment Control

If you don't want to set up TOTP automation:

1. The kill switch will still close all positions
2. You'll receive a Telegram notification with the segment URL
3. Manually deactivate F&O segment on Zerodha Console
4. Takes 30 seconds to do manually

## How It Works

When kill switch is triggered:

1. ✅ Closes all open positions
2. ✅ Stops bot from trading
3. 🤖 Automatically logs into Zerodha Console
4. 🤖 Navigates to segment activation page
5. 🤖 Deactivates F&O (NFO) segment
6. ✅ Sends confirmation via Telegram

This ensures NO new F&O trades can be placed, even if the bot malfunctions.

## Privacy & Security

- Automation runs locally on your machine
- No data is sent to external servers
- Chrome runs in headless mode (background)
- Session is closed immediately after action
- TOTP key never leaves your machine

---

**Ready to test?** Run:
```bash
python segment_automation.py
```
