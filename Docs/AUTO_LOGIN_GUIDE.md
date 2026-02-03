# Automated Daily Login Guide

Complete guide to setup automatic access token generation at 9:15 AM every weekday.

## 📋 Prerequisites

1. **TOTP Key Configured:**
   - Follow [TOTP_SETUP.md](TOTP_SETUP.md) to get your TOTP key
   - Add to `.env`: `KITE_TOTP_KEY=your_key_here`

2. **Chrome/Chromium Installed:**
   - Windows: Chrome auto-installs with Selenium
   - Ubuntu: `sudo apt install chromium-browser chromium-chromedriver`

3. **Credentials in .env:**
   ```env
   KITE_USER_ID=YS2567
   KITE_PASSWORD=your_password
   KITE_TOTP_KEY=your_totp_key
   ```

---

## 🪟 Windows Setup

### Method 1: Task Scheduler (Recommended)

1. **Run Setup Script (as Administrator):**
   ```powershell
   # Right-click PowerShell -> Run as Administrator
   cd kite-algo
   .\setup_daily_login_windows.ps1
   ```

2. **Test Immediately:**
   ```bash
   python auto_login.py
   ```

3. **Verify Task Created:**
   - Open Task Scheduler
   - Look for "KiteAutoLogin"
   - Should run at 9:15 AM Mon-Fri

### Method 2: Manual Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Name: "Kite Auto Login"
4. Trigger: Daily at 9:15 AM
5. Action: Start a program
   - Program: `C:\path\to\kite-algo\.venv\Scripts\python.exe`
   - Arguments: `auto_login.py`
   - Start in: `C:\path\to\kite-algo`
6. Conditions: Only run on weekdays

---

## 🐧 Ubuntu/Linux Setup

### Method 1: Systemd Service (Recommended)

1. **Run Setup Script:**
   ```bash
   chmod +x setup_daily_login.sh
   ./setup_daily_login.sh
   # Select option 1
   ```

2. **Verify Service:**
   ```bash
   sudo systemctl status kite-daily-startup
   ```

3. **View Logs:**
   ```bash
   sudo journalctl -u kite-daily-startup -f
   ```

### Method 2: Cron Job

1. **Run Setup Script:**
   ```bash
   ./setup_daily_login.sh
   # Select option 2
   ```

2. **Verify Cron Job:**
   ```bash
   crontab -l
   ```

3. **View Logs:**
   ```bash
   tail -f logs/auto_login.log
   ```

### Method 3: Manual Cron Setup

```bash
# Edit crontab
crontab -e

# Add this line (runs at 9:15 AM Mon-Fri)
15 9 * * 1-5 cd /home/ubuntu/kite-algo && /home/ubuntu/kite-algo/venv/bin/python /home/ubuntu/kite-algo/auto_login.py >> /home/ubuntu/kite-algo/logs/auto_login.log 2>&1
```

---

## 🧪 Testing

### Test Auto-Login Now

**Windows:**
```bash
python auto_login.py
```

**Linux:**
```bash
source venv/bin/activate
python auto_login.py
```

### Test with Scheduler

**Windows:**
```powershell
Start-ScheduledTask -TaskName "KiteAutoLogin"
```

**Linux (Systemd):**
```bash
# Run startup immediately
python daily_startup.py --now
```

**Linux (Cron):**
```bash
# Manually trigger
cd ~/kite-algo && venv/bin/python auto_login.py
```

---

## 📊 How It Works

### Daily Flow (9:15 AM)

1. **Scheduler triggers** at 9:15 AM (Mon-Fri only)
2. **Auto-login script runs:**
   - Opens Chrome in headless mode
   - Navigates to Kite login
   - Enters user ID and password
   - Generates TOTP code automatically
   - Enters TOTP and completes login
   - Extracts request token from redirect URL
   - Generates access token using Kite API
   - Saves token to `access_token.txt`
3. **Services restart** (Linux only)
4. **Telegram notification** sent
5. **Bot ready to trade**

### What Happens

```
09:15:00 - Scheduler triggers
09:15:05 - Chrome opens (headless)
09:15:10 - Login form filled
09:15:15 - TOTP generated and entered
09:15:20 - Redirect captured
09:15:25 - Access token generated
09:15:30 - Token saved
09:15:35 - Services restarted
09:15:40 - Telegram notification sent
09:15:45 - Bot starts trading
```

---

## 📱 Telegram Notifications

You'll receive notifications for:

**Success:**
```
🌅 DAILY STARTUP COMPLETE

Time: 09:15:45
Date: 20-Jan-2026

✅ Access token generated
✅ Services restarted
✅ Bot is ready to trade

Send /status to check bot status
```

**Failure:**
```
⚠️ DAILY STARTUP FAILED

Time: 09:15:30
Date: 20-Jan-2026

❌ Token generation failed

Please login manually:
`python login.py`
```

---

## 🔧 Troubleshooting

### Auto-Login Fails

**Check TOTP Key:**
```bash
python -c "import pyotp; print(pyotp.TOTP('YOUR_KEY').now())"
# Should match your authenticator app
```

**Check Chrome:**
```bash
# Windows
where chrome

# Linux
which chromium-browser
chromium-browser --version
```

**Check Credentials:**
```bash
# Verify .env file
cat .env | grep KITE_
```

**Run in Non-Headless Mode:**
Edit `auto_login.py`:
```python
auto_login = AutoLogin(headless=False)  # See what's happening
```

### Task Not Running

**Windows:**
```powershell
# Check task status
Get-ScheduledTask -TaskName "KiteAutoLogin"

# Check task history
Get-ScheduledTaskInfo -TaskName "KiteAutoLogin"

# Run manually
Start-ScheduledTask -TaskName "KiteAutoLogin"
```

**Linux (Systemd):**
```bash
# Check service status
sudo systemctl status kite-daily-startup

# Check logs
sudo journalctl -u kite-daily-startup -n 50

# Restart service
sudo systemctl restart kite-daily-startup
```

**Linux (Cron):**
```bash
# Check cron is running
sudo systemctl status cron

# Check cron logs
grep CRON /var/log/syslog

# Test cron job manually
cd ~/kite-algo && venv/bin/python auto_login.py
```

### Chrome Issues

**Linux - Install Chrome:**
```bash
sudo apt update
sudo apt install -y chromium-browser chromium-chromedriver
```

**Linux - Headless Issues:**
```bash
# Install dependencies
sudo apt install -y xvfb libgbm1 libnss3 libxss1 libasound2
```

**Check Chrome Driver:**
```bash
# Should auto-install, but if issues:
pip install --upgrade webdriver-manager
```

---

## 🔐 Security Considerations

### TOTP Key Security

⚠️ **IMPORTANT:**
- TOTP key is as sensitive as your password
- Store `.env` file securely
- Never commit to git
- Use file permissions: `chmod 600 .env`

### Headless Mode

- Chrome runs in background (headless)
- No GUI displayed
- Logs saved for debugging
- Screenshots on errors

### Access Token

- Token saved to `access_token.txt`
- Valid for one day only
- Automatically regenerated daily
- Old tokens become invalid

---

## 📅 Schedule Customization

### Change Time

**Windows Task Scheduler:**
- Open Task Scheduler
- Edit "KiteAutoLogin" task
- Change trigger time

**Linux Cron:**
```bash
crontab -e
# Change: 15 9 * * 1-5
# Format: minute hour day month weekday
# Example: 30 9 * * 1-5 (9:30 AM)
```

**Linux Systemd:**
Edit `daily_startup.py`:
```python
schedule.every().monday.at("09:30").do(self.run_daily_startup)
```

### Add Weekend Trading

Edit `auto_login.py`:
```python
def is_weekday(self):
    return True  # Run every day
```

---

## 📊 Monitoring

### Check Last Run

**Windows:**
```powershell
Get-ScheduledTaskInfo -TaskName "KiteAutoLogin" | Select LastRunTime, LastTaskResult
```

**Linux:**
```bash
# Systemd
sudo journalctl -u kite-daily-startup -n 1

# Cron
tail -n 20 logs/auto_login.log
```

### View Logs

**All Platforms:**
```bash
# Auto-login logs
tail -f logs/auto_login.log

# Daily startup logs
tail -f logs/daily_startup.log

# Bot logs
tail -f logs/bot.log
```

---

## ✅ Verification Checklist

Before going live:

- [ ] TOTP key configured and tested
- [ ] Chrome/Chromium installed
- [ ] Auto-login tested manually
- [ ] Scheduler/cron job created
- [ ] Test run successful
- [ ] Telegram notifications working
- [ ] Services restart after token generation
- [ ] Logs being written
- [ ] Bot starts trading after auto-login

---

## 🎯 Best Practices

1. **Test First:**
   - Run `python auto_login.py` manually
   - Verify token is generated
   - Check bot can connect

2. **Monitor Initially:**
   - Watch logs for first few days
   - Verify daily execution
   - Check Telegram notifications

3. **Backup Plan:**
   - Keep manual login process ready
   - Monitor Telegram for failures
   - Have `login.py` accessible

4. **Regular Checks:**
   - Weekly: Verify auto-login working
   - Monthly: Check logs for errors
   - Quarterly: Update dependencies

---

## 📞 Support

If auto-login fails:

1. Check Telegram for error notification
2. View logs: `tail -f logs/auto_login.log`
3. Test manually: `python auto_login.py`
4. Verify TOTP: Compare with authenticator app
5. Fallback: Run `python login.py` manually

---

**Your bot will now automatically login every weekday at 9:15 AM! 🎉**

No more manual token generation - fully automated trading system!
