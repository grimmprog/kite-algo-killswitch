# AWS Ubuntu Server Deployment Guide

Complete guide to deploy your Kite Algo Trading Bot on AWS Ubuntu server for 24/7 operation.

## 📋 Table of Contents
- [Prerequisites](#prerequisites)
- [AWS Setup](#aws-setup)
- [Server Setup](#server-setup)
- [Bot Installation](#bot-installation)
- [Running as Service](#running-as-service)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### AWS Account
- Active AWS account
- Basic understanding of EC2

### Local Requirements
- SSH client (PuTTY for Windows, built-in for Mac/Linux)
- Your bot files ready to upload

---

## AWS Setup

### 1. Launch EC2 Instance

1. **Login to AWS Console:**
   - Go to EC2 Dashboard
   - Click "Launch Instance"

2. **Choose AMI:**
   - Select: **Ubuntu Server 22.04 LTS (HVM), SSD Volume Type**
   - Architecture: 64-bit (x86)

3. **Choose Instance Type:**
   - Recommended: **t2.micro** (Free tier eligible)
   - For production: **t2.small** or **t3.small**
   - Memory: At least 1GB RAM

4. **Configure Instance:**
   - Number of instances: 1
   - Network: Default VPC
   - Auto-assign Public IP: Enable

5. **Add Storage:**
   - Size: 8-20 GB (default 8GB is sufficient)
   - Volume Type: General Purpose SSD (gp2)

6. **Configure Security Group:**
   - Create new security group
   - Add rules:
     ```
     SSH (22) - Your IP (for security)
     Custom TCP (8000) - Your IP (optional, for web interface)
     ```

7. **Key Pair:**
   - Create new key pair
   - Name: `kite-bot-key`
   - Download `.pem` file
   - **IMPORTANT:** Save this file securely!

8. **Launch Instance**
   - Wait for instance to be "Running"
   - Note the Public IP address

### 2. Connect to Server

**From Windows (using PuTTY):**
```bash
# Convert .pem to .ppk using PuTTYgen
# Then connect using PuTTY with:
# Host: ubuntu@YOUR_PUBLIC_IP
# Auth: Use .ppk file
```

**From Mac/Linux:**
```bash
# Set permissions
chmod 400 kite-bot-key.pem

# Connect
ssh -i kite-bot-key.pem ubuntu@YOUR_PUBLIC_IP
```

---

## Server Setup

### 1. Update System

```bash
sudo apt update
sudo apt upgrade -y
```

### 2. Install Python 3.11

```bash
sudo apt install -y python3.11 python3.11-venv python3-pip
```

### 3. Install Chrome/Chromium (for Selenium)

```bash
# Install Chromium browser
sudo apt install -y chromium-browser chromium-chromedriver

# Verify installation
chromium-browser --version
chromedriver --version
```

### 4. Install System Dependencies

```bash
# For Chrome headless mode
sudo apt install -y xvfb

# For building Python packages
sudo apt install -y build-essential libssl-dev libffi-dev python3-dev

# For TA-Lib (if using technical indicators)
sudo apt install -y libta-lib0-dev
```

---

## Bot Installation

### 1. Create Bot Directory

```bash
mkdir -p ~/kite-algo
cd ~/kite-algo
```

### 2. Upload Bot Files

**Option A: Using SCP (from your local machine):**
```bash
# From your local machine
scp -i kite-bot-key.pem -r kite-algo/* ubuntu@YOUR_PUBLIC_IP:~/kite-algo/
```

**Option B: Using Git:**
```bash
# On server
git clone YOUR_REPO_URL ~/kite-algo
cd ~/kite-algo
```

**Option C: Manual Upload:**
- Use FileZilla or WinSCP
- Connect using your .pem key
- Upload all files to `~/kite-algo/`

### 3. Create Virtual Environment

```bash
cd ~/kite-algo
python3.11 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Configure Environment

```bash
# Create .env file
nano .env
```

Add your credentials:
```env
KITE_API_KEY=your_api_key
KITE_API_SECRET=your_api_secret
KITE_REDIRECT_URL=https://kite.zerodha.com/connect/login
KITE_USER_ID=YS2567
KITE_PASSWORD=your_password
KITE_TOTP_KEY=your_totp_key

TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Save: `Ctrl+X`, then `Y`, then `Enter`

### 6. Test Installation

```bash
# Test connection
python test_connection.py

# Test Telegram
python verify_telegram.py
```

---

## Running as Service

### 1. Create Systemd Service Files

**Main Bot Service:**
```bash
sudo nano /etc/systemd/system/kite-bot.service
```

Add:
```ini
[Unit]
Description=Kite Algo Trading Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/kite-algo
Environment="PATH=/home/ubuntu/kite-algo/venv/bin"
ExecStart=/home/ubuntu/kite-algo/venv/bin/python /home/ubuntu/kite-algo/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Kill Switch Monitor Service:**
```bash
sudo nano /etc/systemd/system/kite-killswitch.service
```

Add:
```ini
[Unit]
Description=Kite Kill Switch Monitor
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/kite-algo
Environment="PATH=/home/ubuntu/kite-algo/venv/bin"
ExecStart=/home/ubuntu/kite-algo/venv/bin/python /home/ubuntu/kite-algo/advanced_killswitch.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Telegram Bot Service:**
```bash
sudo nano /etc/systemd/system/kite-telegram.service
```

Add:
```ini
[Unit]
Description=Kite Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/kite-algo
Environment="PATH=/home/ubuntu/kite-algo/venv/bin"
ExecStart=/home/ubuntu/kite-algo/venv/bin/python /home/ubuntu/kite-algo/test_telegram_commands.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 2. Enable and Start Services

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable services (start on boot)
sudo systemctl enable kite-bot
sudo systemctl enable kite-killswitch
sudo systemctl enable kite-telegram

# Start services
sudo systemctl start kite-bot
sudo systemctl start kite-killswitch
sudo systemctl start kite-telegram

# Check status
sudo systemctl status kite-bot
sudo systemctl status kite-killswitch
sudo systemctl status kite-telegram
```

### 3. Service Management Commands

```bash
# Start service
sudo systemctl start kite-bot

# Stop service
sudo systemctl stop kite-bot

# Restart service
sudo systemctl restart kite-bot

# View logs
sudo journalctl -u kite-bot -f

# View last 100 lines
sudo journalctl -u kite-bot -n 100

# Check status
sudo systemctl status kite-bot
```

---

## Daily Token Generation

Since access tokens expire daily, create a cron job or manual script:

### Option 1: Manual (Recommended for Security)

```bash
# Every morning before market opens
cd ~/kite-algo
source venv/bin/activate
python login.py
```

### Option 2: Automated (Less Secure)

Create a script:
```bash
nano ~/kite-algo/daily_login.sh
```

Add:
```bash
#!/bin/bash
cd /home/ubuntu/kite-algo
source venv/bin/activate
python login.py
sudo systemctl restart kite-bot
```

Make executable:
```bash
chmod +x ~/kite-algo/daily_login.sh
```

Add to crontab:
```bash
crontab -e
```

Add line:
```
0 8 * * 1-5 /home/ubuntu/kite-algo/daily_login.sh
```

---

## Monitoring

### 1. View Logs

```bash
# Real-time logs
tail -f ~/kite-algo/logs/bot.log

# Last 100 lines
tail -n 100 ~/kite-algo/logs/bot.log

# Search logs
grep "ERROR" ~/kite-algo/logs/bot.log
```

### 2. Check System Resources

```bash
# CPU and Memory
htop

# Disk usage
df -h

# Process list
ps aux | grep python
```

### 3. Telegram Monitoring

- Use `/status` command regularly
- Set up alerts for kill switch activation
- Monitor P&L throughout the day

---

## Troubleshooting

### Chrome/Selenium Issues

```bash
# Check Chrome installation
chromium-browser --version

# Test headless mode
chromium-browser --headless --disable-gpu --dump-dom https://www.google.com

# Install missing dependencies
sudo apt install -y libgbm1 libnss3 libxss1 libasound2
```

### Service Not Starting

```bash
# Check logs
sudo journalctl -u kite-bot -n 50

# Check permissions
ls -la /home/ubuntu/kite-algo/

# Test manually
cd ~/kite-algo
source venv/bin/activate
python main.py
```

### Network Issues

```bash
# Test internet connection
ping -c 4 google.com

# Test Kite API
curl https://api.kite.trade/

# Check firewall
sudo ufw status
```

### Memory Issues

```bash
# Check memory
free -h

# If low memory, add swap
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

## Security Best Practices

### 1. Secure SSH

```bash
# Disable password authentication
sudo nano /etc/ssh/sshd_config
# Set: PasswordAuthentication no
sudo systemctl restart sshd
```

### 2. Setup Firewall

```bash
sudo ufw allow 22/tcp
sudo ufw enable
```

### 3. Regular Updates

```bash
# Weekly updates
sudo apt update && sudo apt upgrade -y
```

### 4. Backup Configuration

```bash
# Backup .env and important files
tar -czf kite-backup-$(date +%Y%m%d).tar.gz ~/kite-algo/.env ~/kite-algo/access_token.txt
```

---

## Cost Optimization

### AWS Free Tier
- t2.micro: 750 hours/month free for 12 months
- After free tier: ~$8-10/month

### Reduce Costs
1. Stop instance when not trading
2. Use spot instances (advanced)
3. Schedule start/stop with Lambda

### Auto Start/Stop Script

```bash
# Stop at market close
0 16 * * 1-5 sudo shutdown -h now

# Start before market open (use AWS Lambda or CloudWatch)
```

---

## Monitoring Dashboard (Optional)

Install monitoring tools:

```bash
# Install Grafana and Prometheus (optional)
sudo apt install -y prometheus grafana

# Or use simple web dashboard
python server.py  # If you have web interface
```

---

## Quick Reference

### Essential Commands

```bash
# Connect to server
ssh -i kite-bot-key.pem ubuntu@YOUR_IP

# Activate environment
cd ~/kite-algo && source venv/bin/activate

# View logs
tail -f logs/bot.log

# Restart bot
sudo systemctl restart kite-bot

# Check status
sudo systemctl status kite-bot kite-killswitch kite-telegram
```

### File Locations

```
/home/ubuntu/kite-algo/          # Bot directory
/home/ubuntu/kite-algo/logs/     # Log files
/etc/systemd/system/kite-*.service  # Service files
/home/ubuntu/kite-algo/.env      # Configuration
```

---

## Support

For issues:
1. Check logs: `tail -f ~/kite-algo/logs/bot.log`
2. Check service status: `sudo systemctl status kite-bot`
3. Test manually: `python main.py`
4. Check Telegram bot: Send `/status`

---

**Your bot is now running 24/7 on AWS! 🚀**

Monitor via Telegram and check logs regularly.
