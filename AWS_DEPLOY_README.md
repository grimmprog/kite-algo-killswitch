# 🚀 AWS Deployment - Start Here

## Quick Start (5 Minutes)

### Step 1: Pre-Flight Check (Local Machine)
```bash
cd kite-algo
./pre_deploy_check.sh
```
This validates your configuration before deployment.

### Step 2: Upload to AWS
```bash
scp -i your-key.pem -r kite-algo ubuntu@your-ec2-ip:~/
```

### Step 3: Deploy (On AWS)
```bash
ssh -i your-key.pem ubuntu@your-ec2-ip
cd ~/kite-algo
./aws_deploy.sh
```

### Step 4: Start Service
```bash
sudo systemctl start kite-trading-bot
sudo systemctl enable kite-trading-bot
```

### Step 5: Verify
```bash
./check_monitor_status.sh
```
Or send `/status` to your Telegram bot.

---

## 📚 Documentation

| File | Purpose |
|------|---------|
| **DEPLOYMENT_SUMMARY.md** | Overview and quick guide |
| **AWS_DEPLOYMENT_COMPLETE.md** | Detailed deployment guide |
| **AWS_QUICK_REFERENCE.md** | Command reference card |

---

## 🛠️ Scripts

| Script | Purpose |
|--------|---------|
| `pre_deploy_check.sh` | Validate before deployment |
| `aws_deploy.sh` | Automated deployment |
| `check_monitor_status.sh` | Check monitoring status |
| `start_bot_with_monitor.py` | Main startup script |

---

## 🎯 What Gets Deployed

✅ **Auto-Login** - Runs at 8:45 AM weekdays
✅ **Continuous Monitoring** - Checks P&L every 5 seconds
✅ **Kill Switch** - Auto-deactivates segments on trigger
✅ **Telegram Bot** - Full control via mobile
✅ **Auto-Restart** - Recovers from crashes
✅ **Logging** - Complete audit trail

---

## 📊 Monitoring

### Kill Switch Triggers
- Loss > ₹4,000
- Profit drawdown: Peak ₹5,000 → Drop ₹2,000

### When Triggered
1. Warning sent (30s before)
2. Positions closed
3. F&O segment deactivated
4. Confirmation sent
5. Monitoring stops

---

## 💬 Telegram Commands

```
/status       - Bot and monitoring status
/monitor      - Start monitoring
/stopmonitor  - Stop monitoring
/segments     - Manage segments
```

---

## 🔧 Service Management

```bash
# Start/Stop
sudo systemctl start kite-trading-bot
sudo systemctl stop kite-trading-bot
sudo systemctl restart kite-trading-bot

# Status
sudo systemctl status kite-trading-bot

# Logs
tail -f logs/bot_monitor.log
```

---

## 🆘 Emergency

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

---

## 💰 AWS Cost

- **Recommended**: t2.small (~$17/month)
- **Testing**: t2.micro (free tier)
- **Production**: t2.medium (~$34/month)

---

## ✅ Success Checklist

After deployment, verify:

- [ ] Service is running: `sudo systemctl status kite-trading-bot`
- [ ] Monitoring is active: `./check_monitor_status.sh`
- [ ] Telegram responds: `/status`
- [ ] Auto-login scheduled: `crontab -l`
- [ ] No errors in logs: `tail logs/bot_monitor.log`

---

## 📞 Need Help?

1. Check `DEPLOYMENT_SUMMARY.md` for overview
2. Read `AWS_DEPLOYMENT_COMPLETE.md` for details
3. Use `AWS_QUICK_REFERENCE.md` for commands
4. Run `./check_monitor_status.sh` for diagnostics

---

## 🎉 You're Ready!

Follow the Quick Start above to deploy in 5 minutes.

**Your bot will protect your account 24/7!**
