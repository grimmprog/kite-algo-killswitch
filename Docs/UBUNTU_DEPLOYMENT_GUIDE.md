# Ubuntu Server Deployment Guide

Complete guide for deploying the Kite Algo Trading Bot on Ubuntu server with automated daily login.

## Prerequisites

- Ubuntu 20.04 or later
- Python 3.8+
- Chrome/Chromium browser
- Sudo access

## Step 1: Initial Server Setup

### 1.1 Update System
```bash
sudo apt update
sudo apt upgrade -y
```

### 1.2 Install Python and Dependencies
```bash
sudo apt install -y python3 python3-pip python3-venv
sudo apt install -y chromium-browser chromium-chromedriver
```

### 1.3 Install System Dependencies
```bash
# For Selenium
sudo apt install -y wget unzip xvfb

# For headless Chrome
sudo apt install -y libglib2.0-0 libnss3 libgconf-2-4 libfontconfig1
```

## Step 2: Project Setup

### 2.1 Clone/Upload Project
```bash
cd ~
mkdir -p trading
cd trading

# Upload your project files here
# Or use git clone if you have a repository
```

### 2.2 Create Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2.3 Install Python Packages
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Step 3: Configuration

### 3.1 Configure Environment Variables
```bash
nano .env
```

Make sure these are set:
```env
# Kite API
KITE_API_KEY=your_api_key
KITE_API_SECRET=your_api_secret
KITE_USER_ID=your_user_id
KITE_PASSWORD=your_password
KITE_TOTP_KEY=your_totp_key

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Other settings
CAPITAL=40000
MAX_DAILY_LOSS=4000
```

### 3.2 Test TOTP
```bash
python test_totp.py
```

Should show matching codes with Google Authenticator.

### 3.3 Test Auto-Login
```bash
python auto_login.py
```

Should complete successfully and create `access_token.txt`.

## Step 4: Setup Cron Jobs

### 4.1 Create Log Directory
```bash
mkdir -p ~/trading/logs
```

### 4.2 Create Auto-Login Script
```bash
nano ~/trading/daily_login.sh
```

Add this content:
```bash
#!/bin/bash

# Daily Auto-Login Script
# Runs every weekday morning to generate access token

# Set working directory
cd /home/YOUR_USERNAME/trading

# Activate virtual environment
source .venv/bin/activate

# Run auto-login
python auto_login.py >> logs/autologin_$(date +\%Y\%m\%d).log 2>&1

# Deactivate
deactivate
```

Make it executable:
```bash
chmod +x ~/trading/daily_login.sh
```

### 4.3 Create Bot Startup Script
```bash
nano ~/trading/start_telegram_bot.sh
```

Add this content:
```bash
#!/bin/bash

# Telegram Bot Startup Script
# Starts the full-featured Telegram bot

# Set working directory
cd /home/YOUR_USERNAME/trading

# Activate virtual environment
source .venv/bin/activate

# Kill any existing bot instances
pkill -f "python.*telegram_bot.py"

# Start bot
nohup python telegram_bot.py >> logs/telegram_bot_$(date +\%Y\%m\%d).log 2>&1 &

echo "Telegram bot started. PID: $!"
```

Make it executable:
```bash
chmod +x ~/trading/start_telegram_bot.sh
```

### 4.4 Setup Cron Jobs
```bash
crontab -e
```

Add these lines:
```cron
# Auto-login every weekday at 8:45 AM (before market opens at 9:15 AM)
45 8 * * 1-5 /home/YOUR_USERNAME/trading/daily_login.sh

# Start Telegram bot every weekday at 8:50 AM
50 8 * * 1-5 /home/YOUR_USERNAME/trading/start_telegram_bot.sh

# Optional: Restart bot at 3:45 PM (after market closes at 3:30 PM)
45 15 * * 1-5 /home/YOUR_USERNAME/trading/start_telegram_bot.sh
```

**Important**: Replace `YOUR_USERNAME` with your actual Ubuntu username!

## Step 5: Systemd Service (Alternative to Cron)

For more robust bot management, use systemd:

### 5.1 Create Service File
```bash
sudo nano /etc/systemd/system/kite-telegram-bot.service
```

Add this content:
```ini
[Unit]
Description=Kite Algo Trading Telegram Bot
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/trading
Environment="PATH=/home/YOUR_USERNAME/trading/.venv/bin"
ExecStart=/home/YOUR_USERNAME/trading/.venv/bin/python telegram_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 5.2 Enable and Start Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable kite-telegram-bot
sudo systemctl start kite-telegram-bot
```

### 5.3 Check Status
```bash
sudo systemctl status kite-telegram-bot
```

### 5.4 View Logs
```bash
sudo journalctl -u kite-telegram-bot -f
```

## Step 6: Testing

### 6.1 Test Auto-Login Manually
```bash
cd ~/trading
./daily_login.sh
```

Check logs:
```bash
tail -f logs/autologin_*.log
```

### 6.2 Test Telegram Bot
```bash
./start_telegram_bot.sh
```

In Telegram, send:
```
/start
/status
```

### 6.3 Test Cron Job
Wait for scheduled time or manually trigger:
```bash
# Run the command from crontab manually
/home/YOUR_USERNAME/trading/daily_login.sh
```

## Step 7: Monitoring

### 7.1 Check Running Processes
```bash
ps aux | grep python
```

### 7.2 Check Logs
```bash
# Auto-login logs
ls -lh ~/trading/logs/autologin_*.log
tail -f ~/trading/logs/autologin_$(date +%Y%m%d).log

# Telegram bot logs
tail -f ~/trading/logs/telegram_bot_$(date +%Y%m%d).log
```

### 7.3 Check Cron Logs
```bash
grep CRON /var/log/syslog | tail -20
```

## Step 8: Maintenance

### 8.1 Update Code
```bash
cd ~/trading
source .venv/bin/activate
git pull  # if using git
pip install -r requirements.txt --upgrade
```

### 8.2 Restart Services
```bash
# If using systemd
sudo systemctl restart kite-telegram-bot

# If using cron
pkill -f "python.*telegram_bot.py"
./start_telegram_bot.sh
```

### 8.3 Clean Old Logs
```bash
# Keep only last 30 days of logs
find ~/trading/logs -name "*.log" -mtime +30 -delete
```

## Troubleshooting

### Auto-Login Fails

**Check Chrome/Chromium:**
```bash
chromium-browser --version
which chromedriver
```

**Check TOTP sync:**
```bash
cd ~/trading
source .venv/bin/activate
python test_totp.py
```

**Check logs:**
```bash
tail -100 ~/trading/logs/autologin_*.log
```

**Common issues:**
- TOTP out of sync → Run `python fix_totp_time_sync.py`
- Chrome not found → Install: `sudo apt install chromium-browser`
- Display error → Chrome is running in headless mode, should work

### Telegram Bot Not Responding

**Check if running:**
```bash
ps aux | grep telegram_bot.py
```

**Check logs:**
```bash
tail -100 ~/trading/logs/telegram_bot_*.log
```

**Restart:**
```bash
pkill -f "python.*telegram_bot.py"
./start_telegram_bot.sh
```

**Check bot token:**
```bash
grep TELEGRAM_BOT_TOKEN ~/trading/.env
```

### Cron Job Not Running

**Check cron service:**
```bash
sudo systemctl status cron
```

**Check crontab:**
```bash
crontab -l
```

**Check syslog:**
```bash
grep CRON /var/log/syslog | tail -20
```

**Test script manually:**
```bash
/home/YOUR_USERNAME/trading/daily_login.sh
```

## Security Best Practices

### 1. Secure .env File
```bash
chmod 600 ~/trading/.env
```

### 2. Secure Access Token
```bash
chmod 600 ~/trading/access_token.txt
```

### 3. Use SSH Keys
```bash
# On your local machine
ssh-keygen -t ed25519
ssh-copy-id user@your-server

# Disable password auth
sudo nano /etc/ssh/sshd_config
# Set: PasswordAuthentication no
sudo systemctl restart sshd
```

### 4. Setup Firewall
```bash
sudo ufw allow 22/tcp  # SSH
sudo ufw enable
```

### 5. Regular Updates
```bash
# Add to crontab
0 2 * * 0 sudo apt update && sudo apt upgrade -y
```

## Daily Workflow

### Morning (Automated)
1. **8:45 AM** - Auto-login runs, generates access token
2. **8:50 AM** - Telegram bot starts
3. **9:00 AM** - You receive "Auto-Login Successful" notification

### During Market Hours
- Monitor via Telegram: `/status`, `/positions`
- Auto-monitoring watches for kill switch conditions
- Receive notifications for important events

### After Market Close
- Bot continues running for after-hours monitoring
- Logs are saved for review

## Backup Strategy

### 1. Backup Configuration
```bash
# Create backup script
nano ~/trading/backup.sh
```

```bash
#!/bin/bash
BACKUP_DIR=~/trading_backups
mkdir -p $BACKUP_DIR
DATE=$(date +%Y%m%d)

# Backup important files
tar -czf $BACKUP_DIR/trading_backup_$DATE.tar.gz \
    ~/trading/.env \
    ~/trading/access_token.txt \
    ~/trading/killswitch_status.json \
    ~/trading/logs

# Keep only last 7 backups
ls -t $BACKUP_DIR/trading_backup_*.tar.gz | tail -n +8 | xargs rm -f
```

### 2. Schedule Backups
```bash
# Add to crontab
0 16 * * 1-5 /home/YOUR_USERNAME/trading/backup.sh
```

## Performance Optimization

### 1. Reduce Log Size
```bash
# Rotate logs daily
nano ~/trading/rotate_logs.sh
```

```bash
#!/bin/bash
cd ~/trading/logs
gzip *_$(date -d "yesterday" +%Y%m%d).log 2>/dev/null
find . -name "*.log.gz" -mtime +7 -delete
```

### 2. Monitor Resource Usage
```bash
# Check memory
free -h

# Check disk
df -h

# Check CPU
top
```

---

## Quick Reference

### Start/Stop Commands
```bash
# Start bot
./start_telegram_bot.sh

# Stop bot
pkill -f "python.*telegram_bot.py"

# Check if running
ps aux | grep telegram_bot.py

# View logs
tail -f logs/telegram_bot_$(date +%Y%m%d).log
```

### Telegram Commands
```
/start - Show all commands
/status - Quick P&L status
/monitor - Start auto-monitoring
/segments - Manage segments
/killswitch - Check kill switch
```

### Important Files
- `.env` - Configuration
- `access_token.txt` - Daily access token
- `logs/` - All log files
- `killswitch_status.json` - Kill switch state

---

**Deployment Complete!** 🎉

Your bot will now:
- Auto-login every weekday morning
- Start Telegram bot automatically
- Monitor positions and trigger kill switch
- Send notifications for all events
- Run reliably on Ubuntu server

For support, check the logs first, then refer to the troubleshooting section.
