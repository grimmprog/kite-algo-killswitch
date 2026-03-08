# Auto-Login Solution - Complete Guide

## The Problem

Auto-login fails when run by systemd service because:
- Chrome requires a display (DISPLAY environment variable)
- Systemd services run without a display
- Headless Chrome still needs certain display capabilities
- Error: `Chrome failed to start: exited abnormally`

## The Solution

**Don't run auto-login from the service.** Instead:

1. **Manual Login** - Run auto-login manually when needed
2. **Cron Job** - Schedule auto-login daily at 9:10 AM (before market opens)
3. **Service** - Just starts the bot (expects token to exist)

## Setup Instructions

### Step 1: Setup Daily Auto-Login (Recommended)

Run the setup script:
```bash
./setup_daily_autologin_cron.sh
```

This creates a cron job that:
- Runs at 9:10 AM on weekdays (Mon-Fri)
- Generates fresh access token
- Restarts the bot service
- Bot is ready before market opens at 9:15 AM

### Step 2: Initial Login

For the first time or after logout:
```bash
python auto_login.py
```

This generates the access token that the service needs.

### Step 3: Start/Restart Service

```bash
sudo systemctl restart kite-trading-bot
```

The service will:
- Check if access token exists
- Start the bot with monitoring
- NOT attempt auto-login (to avoid Chrome errors)

## Daily Workflow

### Automated (Recommended)
With cron setup, everything happens automatically:
```
9:10 AM → Cron runs auto-login
       → Token generated
       → Service restarts
       → Bot ready at 9:15 AM
```

### Manual
If you prefer manual control:
```bash
# Every morning before trading
python auto_login.py
sudo systemctl restart kite-trading-bot
```

## After Logout

When you use `/logout` in Telegram:

1. **Token is deleted**
2. **Bot stops**
3. **Service keeps restarting** (but fails without token)

To recover:
```bash
# Generate new token
python auto_login.py

# Restart service
sudo systemctl restart kite-trading-bot
```

## Verify Setup

### Check Cron Job
```bash
crontab -l
```

Should show:
```
10 9 * * 1-5 cd /home/ubuntu/Kite-trading/kite-algo && ...
```

### Check Service Status
```bash
sudo systemctl status kite-trading-bot
```

Should show: `Active: active (running)`

### Check Token
```bash
ls -la access_token.txt
cat access_token.txt
```

Should show a 32-character token.

### Test in Telegram
```
/status
```

Should show actual P&L, not ₹0.00.

## Troubleshooting

### Service Keeps Restarting
**Cause:** No access token found

**Fix:**
```bash
python auto_login.py
sudo systemctl restart kite-trading-bot
```

### Auto-Login Fails
**Cause:** Chrome display issues

**Check:**
```bash
# Test auto-login manually
python auto_login.py

# Check logs
tail -f logs/auto_login_cron.log
```

**Common issues:**
- Chrome not installed: `sudo apt install google-chrome-stable`
- Missing dependencies: `sudo apt install xvfb`
- TOTP key not configured in `.env`

### Cron Job Not Running
**Check cron logs:**
```bash
grep CRON /var/log/syslog | tail -20
```

**Test cron command manually:**
```bash
cd /home/ubuntu/Kite-trading/kite-algo
.venv/bin/python auto_login.py
```

### Bot Shows ₹0.00 P&L
**Cause:** Invalid or expired token

**Fix:**
```bash
# Regenerate token
python auto_login.py

# Reconnect in Telegram
/reconnect
```

## Files Overview

### Scripts
- `auto_login.py` - Automated login with TOTP
- `start_trading_bot.sh` - Service wrapper (checks token, starts bot)
- `setup_daily_autologin_cron.sh` - Setup cron job
- `logout.py` - Manual logout script

### Service
- `kite-trading-bot.service` - Systemd service file
- Runs `start_trading_bot.sh`
- Does NOT run auto-login

### Logs
- `logs/auto_login_cron.log` - Cron auto-login logs
- `logs/bot_service.log` - Service stdout
- `logs/bot_service_error.log` - Service errors

## Best Practices

### 1. Use Cron for Daily Auto-Login
✅ Reliable, runs in user context with display
✅ Automatic, no manual intervention
✅ Logs to dedicated file

### 2. Don't Rely on Service Auto-Login
❌ Chrome display issues
❌ Complex to debug
❌ Not reliable

### 3. Monitor Token Age
The wrapper script shows token age:
```
✅ Access token found (age: 2h)
```

If > 24 hours, regenerate:
```bash
python auto_login.py
```

### 4. Test After Changes
After any configuration change:
```bash
# Test auto-login
python auto_login.py

# Test service
sudo systemctl restart kite-trading-bot
sudo systemctl status kite-trading-bot

# Test bot
/status in Telegram
```

## Summary

**The Right Way:**
```
Cron (9:10 AM) → auto_login.py → Token generated
                                      ↓
Service → start_trading_bot.sh → Check token exists
                                      ↓
                                  Start bot
                                      ↓
                                  Bot ready!
```

**The Wrong Way (Don't Do This):**
```
Service → auto_login.py → Chrome fails → Service crashes
```

## Quick Commands

```bash
# Setup cron (one-time)
./setup_daily_autologin_cron.sh

# Manual login (when needed)
python auto_login.py

# Restart service
sudo systemctl restart kite-trading-bot

# Check status
sudo systemctl status kite-trading-bot

# View logs
tail -f logs/bot_service.log
tail -f logs/auto_login_cron.log

# Test in Telegram
/status
/reconnect
```
