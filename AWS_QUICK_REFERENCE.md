# AWS Deployment - Quick Reference Card

## 🚀 Initial Setup (One-Time)

```bash
# 1. Connect to AWS
ssh -i your-key.pem ubuntu@your-ec2-ip

# 2. Upload files
scp -i your-key.pem -r kite-algo ubuntu@your-ec2-ip:~/

# 3. Configure .env
cd ~/kite-algo
nano .env  # Add your credentials

# 4. Deploy
chmod +x aws_deploy.sh
./aws_deploy.sh

# 5. Start service
sudo systemctl start kite-trading-bot
sudo systemctl enable kite-trading-bot
```

---

## 📊 Service Management

```bash
# Start
sudo systemctl start kite-trading-bot

# Stop
sudo systemctl stop kite-trading-bot

# Restart
sudo systemctl restart kite-trading-bot

# Status
sudo systemctl status kite-trading-bot

# Enable auto-start
sudo systemctl enable kite-trading-bot

# Disable auto-start
sudo systemctl disable kite-trading-bot
```

---

## 📝 View Logs

```bash
# Real-time monitoring
tail -f logs/bot_monitor.log

# Service logs
tail -f logs/bot_service.log

# Errors
tail -f logs/bot_service_error.log

# Auto-login
tail -f logs/auto_login.log

# Last 100 lines
tail -n 100 logs/bot_monitor.log

# Search for errors
grep -i error logs/*.log
```

---

## 💬 Telegram Commands

```
/start          - Welcome message
/status         - Bot status + monitoring state
/monitor        - Start monitoring
/stopmonitor    - Stop monitoring
/segments       - Manage segments
/help           - Command list
```

---

## 🔧 Troubleshooting

### Service Not Running
```bash
sudo systemctl status kite-trading-bot
sudo journalctl -u kite-trading-bot -n 50
```

### Test Manually
```bash
cd ~/kite-algo
source .venv/bin/activate
python start_bot_with_monitor.py
```

### Chrome Issues
```bash
google-chrome --version
sudo apt-get install --reinstall google-chrome-stable
```

### Auto-Login Issues
```bash
crontab -l
cd ~/kite-algo && source .venv/bin/activate && python auto_login.py
```

---

## 🔄 Update Code

```bash
# Stop service
sudo systemctl stop kite-trading-bot

# Update files
cd ~/kite-algo
# Upload new files or git pull

# Restart service
sudo systemctl start kite-trading-bot
```

---

## 💾 Backup

```bash
# Create backup
cd ~
tar -czf kite-backup-$(date +%Y%m%d).tar.gz kite-algo/.env kite-algo/logs

# Download to local
scp -i your-key.pem ubuntu@your-ec2-ip:~/kite-backup-*.tar.gz .
```

---

## 📈 Monitoring Status

### Check if Monitoring is Active
```bash
# Via logs
tail -f logs/bot_monitor.log | grep "monitoring"

# Via Telegram
/status
```

### Verify Kill Switch Settings
```bash
cat .env | grep THRESHOLD
```

---

## 🎯 Kill Switch Behavior

**Triggers:**
- Loss > ₹4,000
- Profit drawdown: Peak ₹5,000 → Drop ₹2,000

**Actions:**
1. Warning sent (30s before)
2. Close all positions
3. Deactivate F&O segment
4. Send confirmation
5. Stop monitoring

---

## 🕐 Scheduled Tasks

### Auto-Login
- **Time**: 8:45 AM (Mon-Fri)
- **Action**: Login to Kite, save token
- **Logs**: `logs/auto_login.log`

### View Cron Jobs
```bash
crontab -l
```

### Edit Cron Jobs
```bash
crontab -e
```

---

## 🔒 Security

```bash
# Secure .env
chmod 600 .env

# Check permissions
ls -la .env

# View who can access
sudo ufw status
```

---

## 💰 Cost Monitoring

```bash
# Check instance type
curl http://169.254.169.254/latest/meta-data/instance-type

# Monitor disk usage
df -h

# Clean old logs
find logs/ -name "*.log" -mtime +7 -delete
```

---

## 🆘 Emergency Actions

### Stop Everything Immediately
```bash
sudo systemctl stop kite-trading-bot
```

### Deactivate All Segments Manually
```bash
cd ~/kite-algo
source .venv/bin/activate
python deactivate_all_segments.py
```

### Check Current Positions
```bash
# Via Telegram
/status
```

---

## 📞 Quick Checks

### Is Bot Running?
```bash
sudo systemctl is-active kite-trading-bot
# Output: active or inactive
```

### Is Monitoring Active?
```bash
tail -n 20 logs/bot_monitor.log | grep "Monitor"
```

### Last Login Time
```bash
tail -n 50 logs/auto_login.log | grep "Login successful"
```

### Recent Errors
```bash
tail -n 100 logs/*.log | grep -i error
```

---

## 🔄 Restart After Changes

```bash
# After changing .env
sudo systemctl restart kite-trading-bot

# After updating code
sudo systemctl restart kite-trading-bot

# After system updates
sudo reboot
```

---

## 📱 Remote Access

### From Mobile (Termux)
```bash
ssh -i ~/.ssh/your-key ubuntu@your-ec2-ip
```

### Quick Status Check
```bash
ssh -i your-key.pem ubuntu@your-ec2-ip "sudo systemctl status kite-trading-bot"
```

---

## ⚡ Performance

### Check CPU/Memory
```bash
top -p $(pgrep -f start_bot_with_monitor)
```

### Check Network
```bash
netstat -tulpn | grep python
```

---

## 📋 Daily Checklist

Morning (9:00 AM):
- [ ] Check `/status` on Telegram
- [ ] Verify monitoring is ON (🟢)
- [ ] Check auto-login succeeded

During Trading:
- [ ] Monitor Telegram notifications
- [ ] Check P&L periodically

Evening (3:30 PM):
- [ ] Review day's logs
- [ ] Check for any errors
- [ ] Verify positions closed

---

## 🎓 Common Scenarios

### Scenario 1: Bot Stopped Working
```bash
sudo systemctl status kite-trading-bot
sudo systemctl restart kite-trading-bot
tail -f logs/bot_service_error.log
```

### Scenario 2: Monitoring Not Active
```bash
# Via Telegram: /monitor
# Or restart service
sudo systemctl restart kite-trading-bot
```

### Scenario 3: Need to Update Thresholds
```bash
nano .env  # Edit LOSS_THRESHOLD, etc.
sudo systemctl restart kite-trading-bot
```

### Scenario 4: Chrome Not Working
```bash
google-chrome --version
sudo apt-get update
sudo apt-get install --reinstall google-chrome-stable
```

---

## 📞 Support Commands

```bash
# System info
uname -a
python3 --version
google-chrome --version

# Service info
sudo systemctl status kite-trading-bot
journalctl -u kite-trading-bot --since today

# Disk space
df -h

# Memory usage
free -h
```

---

**Keep this reference handy for quick operations!**
