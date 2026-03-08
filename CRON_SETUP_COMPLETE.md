# Cron Jobs Setup - Complete

## What Was Done

Split the single cron job into two separate jobs for better reliability:

### 1. User Cron Job (ubuntu user)
- **Time**: 9:10 AM, Monday-Friday
- **Action**: Run auto_login.py to generate access token
- **Why user context**: Chrome needs display access, which user cron provides

### 2. Root Cron Job
- **Time**: 9:11 AM, Monday-Friday  
- **Action**: Restart kite-trading-bot service
- **Why root**: No sudo permission issues, direct systemctl access

## Why This Is Better

**Old approach (single cron job):**
```
9:10 AM → auto_login.py → sudo systemctl restart → FAILS (permission issue)
```

**New approach (split cron jobs):**
```
9:10 AM → auto_login.py → Token generated ✅
9:11 AM → systemctl restart (as root) → Service restarted ✅
9:15 AM → Market opens → Bot ready! ✅
```

## Verify Setup

### Check User Cron
```bash
crontab -l
```

Should show:
```
10 9 * * 1-5 cd /home/ubuntu/Kite-trading/kite-algo && /home/ubuntu/Kite-trading/kite-algo/.venv/bin/python /home/ubuntu/Kite-trading/kite-algo/auto_login.py >> /home/ubuntu/Kite-trading/kite-algo/logs/auto_login_cron.log 2>&1
```

### Check Root Cron
```bash
sudo crontab -l
```

Should show:
```
11 9 * * 1-5 systemctl restart kite-trading-bot
```

### Check Logs Tomorrow

**Auto-login log:**
```bash
tail -f logs/auto_login_cron.log
```

**Service log:**
```bash
sudo journalctl -u kite-trading-bot -f
```

**System cron log:**
```bash
grep CRON /var/log/syslog | grep "Feb 27" | grep "9:1"
```

## Manual Testing

### Test auto-login:
```bash
.venv/bin/python auto_login.py
```

### Test service restart:
```bash
sudo systemctl restart kite-trading-bot
sudo systemctl status kite-trading-bot
```

### Test in Telegram:
```
/status
```

## Troubleshooting

### If auto-login fails at 9:10 AM

Check the log:
```bash
tail -50 logs/auto_login_cron.log
```

Common issues:
- Chrome not installed
- TOTP key incorrect in .env
- Network issues

### If service doesn't restart at 9:11 AM

Check system logs:
```bash
grep "kite-trading-bot" /var/log/syslog | grep "Feb 27" | grep "9:11"
sudo journalctl -u kite-trading-bot | grep "Feb 27" | grep "9:11"
```

Check root cron:
```bash
sudo crontab -l
```

### If bot shows ₹0.00 P&L after restart

Token might be invalid. Regenerate:
```bash
.venv/bin/python auto_login.py
sudo systemctl restart kite-trading-bot
```

Then in Telegram:
```
/reconnect
```

## Daily Workflow

### Automated (Default)
Everything happens automatically:
```
9:10 AM → Auto-login runs
       → Token generated
       → Logged in cron log

9:11 AM → Service restarts
       → Bot picks up new token
       → Ready for trading

9:15 AM → Market opens
       → Bot is already running
```

### Manual (If Needed)
If you need to login outside of scheduled time:
```bash
# Generate token
.venv/bin/python auto_login.py

# Restart service
sudo systemctl restart kite-trading-bot

# Verify in Telegram
/status
```

## Files

### Scripts
- `setup_split_cron_jobs.sh` - Setup script (run once)
- `auto_login.py` - Auto-login with TOTP
- `start_bot_with_monitor.py` - Bot with monitoring

### Logs
- `logs/auto_login_cron.log` - Auto-login execution log
- System logs: `/var/log/syslog` - Cron execution log
- Service logs: `journalctl -u kite-trading-bot`

## Quick Commands

```bash
# View all cron jobs
crontab -l              # User cron
sudo crontab -l         # Root cron

# View logs
tail -f logs/auto_login_cron.log
sudo journalctl -u kite-trading-bot -f

# Manual operations
.venv/bin/python auto_login.py
sudo systemctl restart kite-trading-bot
sudo systemctl status kite-trading-bot

# Check tomorrow's execution
grep CRON /var/log/syslog | grep "Feb 27" | grep "9:1"
```

## What to Check Tomorrow (Feb 27)

At 9:12 AM, verify:

1. **Auto-login ran:**
```bash
tail -20 logs/auto_login_cron.log
# Should show "AUTO-LOGIN SUCCESSFUL" with today's timestamp
```

2. **Service restarted:**
```bash
sudo systemctl status kite-trading-bot
# Should show "Active: active (running) since Thu 2026-02-27 09:11"
```

3. **Bot is working:**
```
/status in Telegram
# Should show actual P&L, not ₹0.00
```

4. **Cron executed:**
```bash
grep CRON /var/log/syslog | grep "Feb 27" | grep "ubuntu.*auto_login"
grep CRON /var/log/syslog | grep "Feb 27" | grep "root.*kite-trading-bot"
```

## Success Indicators

✅ Auto-login log shows success at 9:10 AM
✅ Service status shows restart at 9:11 AM  
✅ Telegram /status shows real P&L
✅ No errors in logs
✅ Bot responds to commands

## If It Still Doesn't Work Tomorrow

1. Check system time: `date`
2. Check cron service: `systemctl status cron`
3. Check system uptime: `uptime` (was system running at 9:10 AM?)
4. Run manual test: `.venv/bin/python auto_login.py`
5. Check for errors: `tail -100 logs/auto_login_cron.log`

Then we can investigate further if needed.
