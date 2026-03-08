# 🚀 START HERE - AWS Deployment

## What You're About to Deploy

A fully automated trading protection system that:
- 🤖 Runs 24/7 on AWS Ubuntu
- 📊 Monitors your P&L every 5 seconds
- 🛡️ Automatically deactivates F&O segment when losses exceed ₹4,000
- 📱 Controlled via Telegram from anywhere
- 🔄 Auto-restarts if it crashes
- 📝 Logs everything for audit

---

## 📋 Before You Start

### You Need:
1. ✅ AWS EC2 Ubuntu instance (t2.small recommended)
2. ✅ SSH key to access your instance
3. ✅ Your Kite credentials (user ID, password, TOTP secret)
4. ✅ Telegram bot token and chat ID
5. ✅ 10 minutes of time

### Cost:
- **t2.small**: ~$17/month (~₹1,400/month)
- **t2.micro**: Free tier eligible (for testing)

---

## 🎯 Deployment in 3 Steps

### Step 1: Prepare (Local Machine - 2 minutes)

```bash
# Navigate to your project
cd /path/to/kite-algo

# Run pre-flight check
./pre_deploy_check.sh
```

This validates your `.env` file and all required files.

### Step 2: Upload (Local Machine - 2 minutes)

```bash
# Upload entire folder to AWS
scp -i your-key.pem -r kite-algo ubuntu@your-ec2-ip:~/
```

### Step 3: Deploy (AWS Instance - 5 minutes)

```bash
# Connect to AWS
ssh -i your-key.pem ubuntu@your-ec2-ip

# Navigate to folder
cd ~/kite-algo

# Run deployment script
./aws_deploy.sh

# Start the service
sudo systemctl start kite-trading-bot
sudo systemctl enable kite-trading-bot

# Verify it's running
./check_monitor_status.sh
```

---

## ✅ Verify Deployment

### 1. Check Service Status
```bash
sudo systemctl status kite-trading-bot
```
Should show: `active (running)`

### 2. Check Monitoring
```bash
tail -f logs/bot_monitor.log
```
Should show: `Monitoring started successfully!`

### 3. Test Telegram
Send `/status` to your bot.
Should receive: Bot status with monitoring indicator 🟢 ON

---

## 📚 Documentation Guide

| Read This | When You Need To |
|-----------|------------------|
| **AWS_DEPLOY_README.md** | Quick overview and commands |
| **DEPLOYMENT_SUMMARY.md** | Understand what's deployed |
| **AWS_DEPLOYMENT_COMPLETE.md** | Detailed setup and troubleshooting |
| **AWS_QUICK_REFERENCE.md** | Find commands quickly |
| **DEPLOYMENT_ARCHITECTURE.md** | Understand how it works |

---

## 🎛️ Daily Usage

### Morning (9:00 AM)
```
1. Open Telegram
2. Send: /status
3. Verify: Monitor shows 🟢 ON
```

### During Trading
```
• Bot monitors automatically
• You'll get notifications if triggered
• Check status anytime: /status
```

### Evening (3:30 PM)
```bash
# On AWS (optional)
tail -n 100 logs/bot_monitor.log
```

---

## 🛡️ How Protection Works

### Monitoring (Continuous)
```
Every 5 seconds:
  ├─ Check current P&L
  ├─ Track peak profit
  └─ Evaluate trigger conditions
```

### Trigger Conditions
1. **Loss Threshold**: Loss > ₹4,000
2. **Profit Drawdown**: Peak ₹5,000 → Drop ₹2,000

### When Triggered
```
1. Warning sent (30s before)
2. All positions closed
3. F&O segment deactivated
4. Confirmation sent
5. Monitoring stops
```

### Restart Monitoring
```
Via Telegram: /monitor
Or restart service: sudo systemctl restart kite-trading-bot
```

---

## 💬 Telegram Commands

```
/status       - View bot status and monitoring state
/monitor      - Start monitoring
/stopmonitor  - Stop monitoring
/segments     - Manage trading segments
/help         - Show all commands
```

---

## 🔧 Common Operations

### View Logs
```bash
# Real-time monitoring
tail -f logs/bot_monitor.log

# Service logs
tail -f logs/bot_service.log

# Auto-login logs
tail -f logs/auto_login.log
```

### Restart Service
```bash
sudo systemctl restart kite-trading-bot
```

### Stop Service
```bash
sudo systemctl stop kite-trading-bot
```

### Check Status
```bash
./check_monitor_status.sh
```

---

## 🆘 Emergency Procedures

### Stop Everything
```bash
sudo systemctl stop kite-trading-bot
```

### Deactivate All Segments
```bash
cd ~/kite-algo
source .venv/bin/activate
python deactivate_all_segments.py
```

### Check Positions
```
Send to Telegram: /status
```

---

## 🐛 Troubleshooting

### Service Won't Start
```bash
# Check logs
sudo journalctl -u kite-trading-bot -n 50

# Test manually
cd ~/kite-algo
source .venv/bin/activate
python start_bot_with_monitor.py
```

### Monitoring Not Active
```bash
# Restart service
sudo systemctl restart kite-trading-bot

# Or via Telegram
/monitor
```

### Auto-Login Failed
```bash
# Check logs
tail -f logs/auto_login.log

# Test manually
cd ~/kite-algo
source .venv/bin/activate
python auto_login.py
```

---

## 📊 What Happens Automatically

### Daily (8:45 AM Mon-Fri)
- Auto-login runs
- Access token refreshed
- Notification sent

### Continuous (24/7)
- P&L monitored every 5 seconds
- Peak profit tracked
- Trigger conditions evaluated

### On Trigger
- Positions closed
- F&O segment deactivated
- Notifications sent

### On Crash
- Service restarts automatically
- Monitoring resumes
- Notification sent

---

## 🎓 Learning Path

1. **Start Here** (this file) - Overview
2. **DEPLOYMENT_SUMMARY.md** - What's deployed
3. **AWS_DEPLOY_README.md** - Quick commands
4. **AWS_DEPLOYMENT_COMPLETE.md** - Full details
5. **DEPLOYMENT_ARCHITECTURE.md** - How it works

---

## ✨ Success Indicators

You'll know it's working when:

✅ Service shows "active (running)"
✅ Logs show "Monitoring started successfully"
✅ Telegram `/status` responds
✅ Monitoring shows 🟢 ON
✅ Auto-login cron job scheduled
✅ No errors in logs

---

## 🎉 Ready to Deploy?

Follow these 3 steps:

1. **Prepare**: `./pre_deploy_check.sh`
2. **Upload**: `scp -i key.pem -r kite-algo ubuntu@ip:~/`
3. **Deploy**: `ssh` → `cd ~/kite-algo` → `./aws_deploy.sh`

Then verify with: `./check_monitor_status.sh`

---

## 📞 Need Help?

1. Check logs: `tail -f logs/bot_monitor.log`
2. Run diagnostics: `./check_monitor_status.sh`
3. Read troubleshooting: `AWS_DEPLOYMENT_COMPLETE.md`
4. Test manually: `python start_bot_with_monitor.py`

---

## 🚀 Let's Deploy!

You're ready to protect your trading account 24/7.

**Start with Step 1 above and follow the guide.**

Good luck! 🎯
