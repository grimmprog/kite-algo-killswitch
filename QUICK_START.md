# Quick Start Guide

## 🚀 Get Started in 5 Minutes

### Windows (Local Development)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure .env file
# Edit .env with your credentials

# 3. Generate access token
python login.py

# 4. Test everything
python test_connection.py
python verify_telegram.py

# 5. Start bot
python start_bot.py
```

---

### Ubuntu/AWS (Production)

```bash
# 1. Run setup script
chmod +x ubuntu_setup.sh
./ubuntu_setup.sh

# 2. Configure .env
nano .env

# 3. Generate access token
source venv/bin/activate
python login.py

# 4. Start all services
./start_all.sh

# 5. Check status
./status.sh
```

---

## 📱 Telegram Commands

After bot is running, send these to your Telegram bot:

- `/status` - Quick P&L check
- `/pnl` - Detailed breakdown
- `/positions` - Open positions
- `/killswitch` - Risk status
- `/close` - Emergency close all

---

## 🛡️ Kill Switch

Automatically triggers when:
- Loss > ₹4,000
- Profit ≥ ₹5,000 then drops ₹2,000
- Warning at 10% profit

Actions taken:
1. Closes all positions
2. Stops bot trading
3. Deactivates F&O segment (if TOTP configured)
4. Sends Telegram alert

---

## 📊 Daily Routine

### Morning (Before 9:15 AM)
```bash
# Generate new access token
python login.py

# Start bot (if not running as service)
./start_all.sh  # Linux
# OR
python start_bot.py  # Windows
```

### During Market Hours
- Monitor via Telegram `/status`
- Approve/reject trades
- Watch for kill switch alerts

### Evening (After 3:30 PM)
- Review P&L: `/pnl`
- Check trades: `/orders`
- Review logs

---

## 🔧 Useful Commands

### Linux/Ubuntu
```bash
# Start all
./start_all.sh

# Stop all
./stop_all.sh

# Check status
./status.sh

# View logs
tail -f logs/bot.log

# Restart services
sudo systemctl restart kite-bot
```

### Windows
```bash
# Start bot
python start_bot.py

# Kill switch monitor
python advanced_killswitch.py

# Telegram bot
python test_telegram_commands.py
```

---

## 📚 Documentation

- **README.md** - Complete documentation
- **AWS_DEPLOYMENT.md** - AWS setup guide
- **TOTP_SETUP.md** - Segment automation setup
- **TELEGRAM_SETUP.md** - Telegram bot setup
- **DEPLOYMENT_CHECKLIST.md** - Pre-launch checklist

---

## 🆘 Troubleshooting

### Bot not starting?
```bash
# Check logs
tail -f logs/bot.log

# Test connection
python test_connection.py

# Verify access token
cat access_token.txt
```

### Telegram not working?
```bash
# Test Telegram
python verify_telegram.py

# Check bot token in .env
cat .env | grep TELEGRAM
```

### Kill switch not working?
```bash
# Test kill switch
python kill_switch.py

# Check status
python test_killswitch.py
```

---

## 🎯 Key Files

```
kite-algo/
├── .env                    # Your credentials (KEEP SECRET!)
├── access_token.txt        # Daily access token
├── main.py                 # Main trading bot
├── advanced_killswitch.py  # Kill switch monitor
├── segment_automation.py   # Auto segment control
├── login.py                # Generate access token
├── manual_order.py         # Place manual orders
├── start_all.sh           # Start all (Linux)
├── stop_all.sh            # Stop all (Linux)
├── status.sh              # Check status (Linux)
└── logs/                  # Log files
```

---

## ⚡ Quick Tips

1. **Access Token:** Expires daily - regenerate every morning
2. **Telegram:** Keep bot running for notifications
3. **Kill Switch:** Always run alongside trading bot
4. **Logs:** Check regularly for errors
5. **Backup:** Save .env file securely
6. **TOTP:** Configure for automatic segment control
7. **Testing:** Always test on paper first

---

## 🔐 Security Reminders

- ✅ Never commit .env to git
- ✅ Keep TOTP key secret
- ✅ Use strong passwords
- ✅ Enable 2FA on AWS
- ✅ Restrict SSH access
- ✅ Regular backups

---

## 📞 Need Help?

1. Check logs: `tail -f logs/bot.log`
2. Test components individually
3. Review documentation
4. Check Telegram bot status: `/status`
5. Verify services: `./status.sh`

---

**Happy Trading! 🚀📈**

Remember: Start small, test thoroughly, and always monitor your bot!
