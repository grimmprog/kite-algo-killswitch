# Logout & Auto-Login Test Guide

## Overview
Use the logout feature to test if the service properly runs auto-login on restart.

## Methods to Logout

### Method 1: Telegram Command (Recommended)
```
/logout
```
- Click the button to confirm
- Bot will logout and stop
- Service will auto-restart and run auto-login

### Method 2: Python Script
```bash
python logout.py
```
- Invalidates session on Kite servers
- Deletes local access token file
- Provides instructions for restart

### Method 3: Automated Test Script
```bash
./test_autologin_service.sh
```
- Runs logout
- Restarts service automatically
- Shows live logs to verify auto-login

## What Happens During Logout

1. **Session Invalidation**
   - Calls Kite API to invalidate current token
   - Deletes `access_token.txt` file

2. **Bot Stops** (if using Telegram /logout)
   - Bot exits after 5 seconds
   - Service auto-restarts (due to `Restart=always`)

3. **Auto-Login Runs**
   - Service starts `start_trading_bot.sh`
   - Wrapper runs `auto_login.py` first
   - New access token generated
   - Bot starts with monitoring enabled

## Verify Auto-Login Works

### Watch Service Logs
```bash
sudo journalctl -u kite-trading-bot -f
```

Look for this sequence:
```
KITE TRADING BOT STARTUP
Step 1: Running auto-login...
✅ Auto-login successful!
Step 2: Starting bot with monitoring...
✅ Monitoring started successfully!
```

### Check Access Token
```bash
cat access_token.txt
```
Should show a new token after restart.

### Check Telegram
You should receive a message:
```
✅ Auto-Login Successful

Time: 09:15:23
User: YOUR_USER_ID
Access token generated and saved.

Bot is ready to trade!
```

## Testing Scenarios

### Scenario 1: Test During Market Hours
```bash
# Logout via Telegram
/logout

# Wait 30 seconds, then check status
/status
```

### Scenario 2: Test Service Restart
```bash
# Logout via script
python logout.py

# Restart service
sudo systemctl restart kite-trading-bot

# Watch logs
sudo journalctl -u kite-trading-bot -f
```

### Scenario 3: Full Automated Test
```bash
# Run test script
./test_autologin_service.sh

# Follow prompts and watch logs
```

## Troubleshooting

### Auto-Login Fails
Check logs:
```bash
tail -f logs/bot_service_error.log
```

Common issues:
- TOTP key not configured in `.env`
- Chrome/Chromium not installed
- Wrong credentials
- Network issues

### Bot Doesn't Start After Auto-Login
Check if access token was created:
```bash
ls -la access_token.txt
cat access_token.txt
```

Check service status:
```bash
sudo systemctl status kite-trading-bot
```

### Service Keeps Restarting
View restart count:
```bash
systemctl show kite-trading-bot | grep NRestarts
```

Check what's failing:
```bash
sudo journalctl -u kite-trading-bot -n 100
```

## Manual Recovery

If auto-login fails, login manually:
```bash
python login.py
```

Then restart service:
```bash
sudo systemctl restart kite-trading-bot
```

## Files Involved

- `logout.py` - Logout script
- `auto_login.py` - Auto-login script
- `start_trading_bot.sh` - Wrapper that runs both
- `kite-trading-bot.service` - Systemd service
- `test_autologin_service.sh` - Automated test
- `access_token.txt` - Token storage (deleted on logout)

## Expected Behavior

✅ **Normal Flow:**
1. Logout → Token deleted
2. Service restarts → Auto-login runs
3. Token generated → Bot starts
4. Telegram notification sent

❌ **If Something Fails:**
1. Check logs for errors
2. Verify TOTP configuration
3. Test auto-login manually: `python auto_login.py`
4. Check Chrome is installed: `google-chrome --version`
