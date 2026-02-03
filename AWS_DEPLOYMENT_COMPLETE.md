# AWS Ubuntu Deployment Guide - Complete Setup

## Overview
This guide will help you deploy the Kite Trading Bot on AWS Ubuntu with continuous monitoring and automatic segment deactivation.

## Architecture
```
AWS EC2 Ubuntu Server
├── Auto-Login (Cron: 8:45 AM weekdays)
├── Trading Bot (Systemd Service)
│   ├── Telegram Bot Interface
│   └── Kill Switch Monitor (Continuous)
│       ├── P&L Monitoring (Every 5 seconds)
│       └── Auto Segment Deactivation (On trigger)
└── Logs (Rotating)
```

---

## Prerequisites

### 1. AWS EC2 Instance
- **Instance Type**: t2.small or larger (minimum 2GB RAM)
- **OS**: Ubuntu 22.04 LTS or 20.04 LTS
- **Storage**: 20GB minimum
- **Security Group**: Allow SSH (port 22) from your IP

### 2. Local Requirements
- SSH key pair for EC2 access
- Your Kite credentials and TOTP secret
- Telegram bot token and chat ID

---

## Step-by-Step Deployment

### Step 1: Connect to AWS Instance

```bash
# From your local machine
ssh -i your-key.pem ubuntu@your-ec2-public-ip
```

### Step 2: Upload Project Files

**Option A: Using SCP (from local machine)**
```bash
# Navigate to your project directory
cd /path/to/ZerodhaPythonScripts

# Upload entire kite-algo folder
scp -i your-key.pem -r kite-algo ubuntu@your-ec2-public-ip:~/
```

**Option B: Using Git (on EC2 instance)**
```bash
# On EC2 instance
cd ~
git clone your-repository-url
cd kite-algo
```

### Step 3: Configure Environment Variables

```bash
# On EC2 instance
cd ~/kite-algo

# Create .env file
nano .env
```

Add your credentials:
```bash
# Zerodha Credentials
KITE_USER_ID=AB1234
KITE_PASSWORD=your_password
KITE_TOTP_KEY=PBRCSRYIPJFPZDNLQXZHK6FUN7JQ6KAM

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Kill Switch Thresholds
LOSS_THRESHOLD=4000
PROFIT_THRESHOLD=5000
DRAWDOWN_THRESHOLD=2000
```

Save and exit (Ctrl+X, Y, Enter)

### Step 4: Run Deployment Script

```bash
# Make script executable
chmod +x aws_deploy.sh

# Run deployment
./aws_deploy.sh
```

This script will:
- ✅ Update system packages
- ✅ Install Python 3.10+
- ✅ Install Chrome and ChromeDriver
- ✅ Create virtual environment
- ✅ Install Python dependencies
- ✅ Set up systemd service
- ✅ Configure auto-login cron job
- ✅ Create logs directory

### Step 5: Start the Bot Service

```bash
# Start the service
sudo systemctl start kite-trading-bot

# Enable auto-start on boot
sudo systemctl enable kite-trading-bot

# Check status
sudo systemctl status kite-trading-bot
```

You should see:
```
● kite-trading-bot.service - Kite Trading Bot with Kill Switch Monitoring
   Loaded: loaded (/etc/systemd/system/kite-trading-bot.service; enabled)
   Active: active (running) since ...
```

### Step 6: Verify Monitoring is Active

```bash
# Check logs
tail -f logs/bot_monitor.log
```

You should see:
```
Starting P&L monitoring...
✅ Monitoring started successfully!
Kill switch will trigger on:
  - Loss > ₹4,000
  - Profit drawdown: Peak ₹5,000 → Drop ₹2,000
Bot is now running with active monitoring...
```

---

## Service Management

### Start/Stop/Restart Service
```bash
# Start
sudo systemctl start kite-trading-bot

# Stop
sudo systemctl stop kite-trading-bot

# Restart
sudo systemctl restart kite-trading-bot

# Status
sudo systemctl status kite-trading-bot
```

### View Logs
```bash
# Real-time monitoring logs
tail -f logs/bot_monitor.log

# Service logs
tail -f logs/bot_service.log

# Error logs
tail -f logs/bot_service_error.log

# Auto-login logs
tail -f logs/auto_login.log
```

### Disable Auto-Start
```bash
sudo systemctl disable kite-trading-bot
```

---

## How It Works

### 1. Auto-Login (8:45 AM Weekdays)
- Cron job runs `auto_login.py`
- Logs in to Zerodha Kite
- Saves access token
- Sends Telegram notification

### 2. Continuous Monitoring
- Bot starts with monitoring enabled
- Checks P&L every 5 seconds
- Tracks peak profit for drawdown calculation
- No manual intervention needed

### 3. Kill Switch Trigger
When conditions are met:
1. **Warning sent** (30 seconds before trigger)
2. **Positions closed** (all open positions)
3. **F&O segment deactivated** (via Selenium automation)
4. **Telegram notification** (confirmation sent)
5. **Monitoring stops** (until manually restarted)

### 4. Trigger Conditions
- **Loss Threshold**: Loss exceeds ₹4,000
- **Profit Drawdown**: Peak ₹5,000 → Drop ₹2,000

---

## Telegram Commands

Once deployed, you can control the bot via Telegram:

```
/start - Welcome message
/status - View bot status and monitoring state
/monitor - Start monitoring (if stopped)
/stopmonitor - Stop monitoring
/segments - Manage trading segments
/help - Command reference
```

---

## Monitoring Dashboard

Check monitoring status:
```bash
# Via Telegram
/status

# Via logs
tail -f logs/bot_monitor.log | grep "Monitor"
```

---

## Troubleshooting

### Service Won't Start
```bash
# Check service status
sudo systemctl status kite-trading-bot

# Check logs
sudo journalctl -u kite-trading-bot -n 50

# Verify Python environment
cd ~/kite-algo
source .venv/bin/activate
python start_bot_with_monitor.py
```

### Chrome/ChromeDriver Issues
```bash
# Verify Chrome installation
google-chrome --version

# Reinstall Chrome
sudo apt-get install --reinstall google-chrome-stable

# Test Selenium
cd ~/kite-algo
source .venv/bin/activate
python -c "from selenium import webdriver; print('OK')"
```

### Auto-Login Not Working
```bash
# Check cron jobs
crontab -l

# Test auto-login manually
cd ~/kite-algo
source .venv/bin/activate
python auto_login.py

# Check logs
tail -f logs/auto_login.log
```

### Monitoring Not Active
```bash
# Check if monitoring is running
tail -f logs/bot_monitor.log | grep "monitoring"

# Restart service
sudo systemctl restart kite-trading-bot

# Start monitoring via Telegram
/monitor
```

### High CPU Usage
```bash
# Check process
top -p $(pgrep -f start_bot_with_monitor)

# Adjust monitoring interval in advanced_killswitch.py
# Change: time.sleep(5)  # Check every 5 seconds
# To: time.sleep(10)  # Check every 10 seconds
```

---

## Security Best Practices

### 1. Secure .env File
```bash
chmod 600 .env
```

### 2. Restrict SSH Access
```bash
# Edit SSH config
sudo nano /etc/ssh/sshd_config

# Disable password authentication
PasswordAuthentication no

# Restart SSH
sudo systemctl restart sshd
```

### 3. Set Up Firewall
```bash
# Enable UFW
sudo ufw enable

# Allow SSH
sudo ufw allow 22/tcp

# Check status
sudo ufw status
```

### 4. Regular Updates
```bash
# Update system weekly
sudo apt-get update && sudo apt-get upgrade -y
```

---

## Backup and Recovery

### Backup Configuration
```bash
# Create backup
cd ~
tar -czf kite-algo-backup-$(date +%Y%m%d).tar.gz kite-algo/.env kite-algo/logs

# Download backup to local machine
scp -i your-key.pem ubuntu@your-ec2-ip:~/kite-algo-backup-*.tar.gz .
```

### Restore Configuration
```bash
# Upload backup
scp -i your-key.pem kite-algo-backup-*.tar.gz ubuntu@your-ec2-ip:~/

# Extract
cd ~
tar -xzf kite-algo-backup-*.tar.gz
```

---

## Performance Optimization

### 1. Reduce Memory Usage
```bash
# Run Chrome in headless mode (already configured)
# Adjust monitoring interval if needed
```

### 2. Log Rotation
```bash
# Create logrotate config
sudo nano /etc/logrotate.d/kite-algo
```

Add:
```
/home/ubuntu/kite-algo/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
```

### 3. Monitor Disk Space
```bash
# Check disk usage
df -h

# Clean old logs
find logs/ -name "*.log" -mtime +7 -delete
```

---

## Cost Optimization

### AWS Instance Recommendations
- **Development/Testing**: t2.micro (free tier eligible)
- **Production**: t2.small (2GB RAM, ~$17/month)
- **High Volume**: t2.medium (4GB RAM, ~$34/month)

### Stop Instance When Not Trading
```bash
# Stop instance (from AWS Console or CLI)
aws ec2 stop-instances --instance-ids i-1234567890abcdef0

# Start instance
aws ec2 start-instances --instance-ids i-1234567890abcdef0
```

---

## Monitoring Checklist

Daily:
- [ ] Check bot status via Telegram `/status`
- [ ] Verify monitoring is active
- [ ] Review logs for errors

Weekly:
- [ ] Check disk space
- [ ] Review kill switch triggers
- [ ] Update system packages

Monthly:
- [ ] Backup configuration
- [ ] Review and optimize thresholds
- [ ] Update Python dependencies

---

## Support

If you encounter issues:

1. Check logs: `tail -f logs/bot_monitor.log`
2. Verify service: `sudo systemctl status kite-trading-bot`
3. Test manually: `python start_bot_with_monitor.py`
4. Review this guide's troubleshooting section

---

## Summary

Your bot is now:
✅ Running continuously on AWS
✅ Auto-logging in daily at 8:45 AM
✅ Monitoring P&L every 5 seconds
✅ Auto-deactivating segments on trigger
✅ Sending Telegram notifications
✅ Restarting automatically on crashes

**You're all set! The bot will protect your account 24/7.**
