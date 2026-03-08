# Service Auto-Login Fix

## Problem
The `kite-trading-bot.service` had two `ExecStart` lines, but systemd only executes the last one. This meant `auto_login.py` was never running, so the access token wasn't being generated, and the Telegram bot couldn't start properly.

## Solution
Created a wrapper script that runs both commands sequentially:

1. **start_trading_bot.sh** - Wrapper script that:
   - Runs `auto_login.py` first to generate access token
   - If successful, starts `start_bot_with_monitor.py`
   - If auto-login fails, exits without starting the bot

2. **Updated kite-trading-bot.service** - Now uses the wrapper script as a single `ExecStart`

## How to Apply the Fix

Run the fix script:
```bash
./fix_service_autologin.sh
```

This will:
- Stop the current service
- Update the service file
- Reload systemd
- Restart the service with the fix

## Verify It's Working

Check service status:
```bash
sudo systemctl status kite-trading-bot
```

View live logs:
```bash
sudo journalctl -u kite-trading-bot -f
```

Or check the log file:
```bash
tail -f logs/bot_service.log
```

## What Happens Now

When the service starts:
1. ✅ Auto-login runs and generates access token
2. ✅ Telegram bot starts with monitoring enabled
3. ✅ You receive Telegram notification that login was successful
4. ✅ Bot is ready to trade

## Manual Testing

Test the wrapper script manually:
```bash
./start_trading_bot.sh
```

Test just auto-login:
```bash
python auto_login.py
```

## Troubleshooting

If auto-login fails:
- Check TOTP key is configured in `.env`
- Verify Chrome/Chromium is installed
- Check credentials are correct
- View error logs: `tail -f logs/bot_service_error.log`

If bot doesn't start:
- Check access token exists: `cat access_token.txt`
- Verify Telegram token is configured
- Check service status: `sudo systemctl status kite-trading-bot`

## Files Modified
- `kite-trading-bot.service` - Updated to use wrapper script
- `start_trading_bot.sh` - New wrapper script (created)
- `fix_service_autologin.sh` - Deployment script (created)
