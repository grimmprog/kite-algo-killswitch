# Deployment Checklist

## 📋 Pre-Deployment (Local Testing)

- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file configured with credentials
- [ ] Access token generated (`python login.py`)
- [ ] Kite API connection tested (`python test_connection.py`)
- [ ] Telegram bot configured and tested (`python verify_telegram.py`)
- [ ] Strategy logic verified (`python verify_strategy.py`)
- [ ] Manual order placement tested (`python manual_order.py`)
- [ ] Kill switch tested (`python kill_switch.py`)
- [ ] TOTP key configured for segment automation
- [ ] Segment automation tested (`python segment_automation.py`)

---

## 🖥️ AWS Ubuntu Server Setup

### Initial Setup
- [ ] AWS EC2 instance launched (Ubuntu 22.04)
- [ ] Security group configured (SSH port 22)
- [ ] Key pair downloaded and secured
- [ ] Connected to server via SSH
- [ ] System updated (`sudo apt update && sudo apt upgrade`)

### Bot Installation
- [ ] Bot files uploaded to server
- [ ] Setup script executed (`./ubuntu_setup.sh`)
- [ ] Virtual environment created
- [ ] Dependencies installed
- [ ] `.env` file configured on server
- [ ] Logs directory created
- [ ] Scripts made executable (`chmod +x *.sh`)

### Testing on Server
- [ ] Access token generated
- [ ] Kite connection tested
- [ ] Telegram bot tested
- [ ] Chrome/Selenium working in headless mode
- [ ] Segment automation tested

---

## 🔧 Service Configuration

- [ ] Systemd service files created:
  - [ ] `kite-bot.service`
  - [ ] `kite-killswitch.service`
  - [ ] `kite-telegram.service`
- [ ] Services enabled (`sudo systemctl enable`)
- [ ] Services started (`sudo systemctl start`)
- [ ] Service status verified (`sudo systemctl status`)
- [ ] Logs accessible (`sudo journalctl -u kite-bot`)

---

## 🔐 Security

- [ ] SSH key-based authentication configured
- [ ] Password authentication disabled
- [ ] Firewall configured (`sudo ufw enable`)
- [ ] `.env` file permissions secured (`chmod 600 .env`)
- [ ] TOTP key secured
- [ ] API keys not exposed in logs
- [ ] Backup of configuration created

---

## 📊 Monitoring Setup

- [ ] Telegram commands working:
  - [ ] `/status` - Quick P&L
  - [ ] `/pnl` - Detailed P&L
  - [ ] `/positions` - Open positions
  - [ ] `/orders` - Order history
  - [ ] `/killswitch` - Kill switch status
  - [ ] `/capital` - Capital info
- [ ] Log files accessible
- [ ] Kill switch monitor running
- [ ] Telegram notifications working

---

## 🔄 Daily Operations

- [ ] Access token generation process documented
- [ ] Morning routine established:
  - [ ] Generate new access token
  - [ ] Restart bot services
  - [ ] Verify bot is running
  - [ ] Check Telegram connectivity
- [ ] Evening routine established:
  - [ ] Review day's trades
  - [ ] Check P&L
  - [ ] Verify positions closed
  - [ ] Review logs for errors

---

## 🚨 Kill Switch Verification

- [ ] Kill switch thresholds configured:
  - [ ] Max loss: ₹4,000
  - [ ] Profit protection: ₹5,000 (₹2k drawdown)
  - [ ] Profit warning: 10% of capital
- [ ] Auto-close positions tested
- [ ] Segment deactivation tested
- [ ] Telegram notifications tested
- [ ] Manual activation tested

---

## 📱 Telegram Bot Commands

Test all commands:
- [ ] `/start` - Welcome message
- [ ] `/help` - Command list
- [ ] `/status` - Quick status with buttons
- [ ] `/pnl` - Detailed P&L
- [ ] `/positions` - Open positions
- [ ] `/orders` - Order history
- [ ] `/capital` - Capital and risk info
- [ ] `/killswitch` - Kill switch status
- [ ] `/reactivate` - Reactivate trading
- [ ] `/close` - Close all positions

---

## 🔍 Troubleshooting Checklist

If bot not working:
- [ ] Check service status (`sudo systemctl status kite-bot`)
- [ ] Check logs (`tail -f logs/bot.log`)
- [ ] Verify access token is valid
- [ ] Test Kite API connection
- [ ] Check internet connectivity
- [ ] Verify Chrome/Selenium working
- [ ] Check system resources (memory, CPU)
- [ ] Restart services if needed

---

## 📈 Performance Monitoring

- [ ] Daily P&L tracking
- [ ] Trade journal maintained
- [ ] Win rate calculated
- [ ] Risk metrics monitored
- [ ] System uptime tracked
- [ ] Error rate monitored

---

## 💾 Backup & Recovery

- [ ] Configuration backed up
- [ ] `.env` file backed up securely
- [ ] Access token backup process
- [ ] Recovery procedure documented
- [ ] Backup schedule established

---

## 📚 Documentation

- [ ] README.md reviewed
- [ ] AWS_DEPLOYMENT.md reviewed
- [ ] TOTP_SETUP.md reviewed
- [ ] TELEGRAM_SETUP.md reviewed
- [ ] All commands documented
- [ ] Troubleshooting guide available

---

## ✅ Final Verification

Before going live:
- [ ] All tests passed
- [ ] Services running stable for 24 hours
- [ ] Telegram notifications working
- [ ] Kill switch tested and working
- [ ] Segment automation working
- [ ] Logs being written correctly
- [ ] No errors in logs
- [ ] System resources adequate
- [ ] Backup and recovery tested

---

## 🎯 Go Live Checklist

Day 1:
- [ ] Generate access token
- [ ] Start all services
- [ ] Verify bot is scanning
- [ ] Monitor first trade closely
- [ ] Test kill switch if needed
- [ ] Review end-of-day P&L

Week 1:
- [ ] Monitor daily
- [ ] Review all trades
- [ ] Adjust thresholds if needed
- [ ] Verify stability
- [ ] Document any issues

---

## 📞 Emergency Contacts

- [ ] Telegram bot token saved
- [ ] AWS console access verified
- [ ] Zerodha support number saved
- [ ] Backup access method established

---

**Status:** ⬜ Not Started | 🟡 In Progress | ✅ Complete

**Deployment Date:** _______________

**Deployed By:** _______________

**Notes:**
_______________________________________
_______________________________________
_______________________________________
