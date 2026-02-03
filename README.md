# 🛡️ Kite Algo Kill Switch

An automated trading protection system for Zerodha Kite that monitors your P&L in real-time and automatically deactivates trading segments when loss thresholds are exceeded.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

## 🌟 Features

- **Real-time P&L Monitoring** - Checks your profit/loss every 5 seconds
- **Automatic Protection** - Closes positions and deactivates F&O segment on trigger
- **Telegram Control** - Full remote control via Telegram bot
- **Auto-Login** - Scheduled daily login with TOTP 2FA
- **Segment Management** - Activate/deactivate trading segments remotely
- **AWS Deployment Ready** - Complete deployment scripts for Ubuntu
- **Auto-Restart** - Systemd service with automatic recovery
- **Comprehensive Logging** - Complete audit trail of all actions

## 📊 How It Works

### Trigger Conditions

The kill switch triggers when either condition is met:

1. **Loss Threshold**: Total loss exceeds configured percentage or amount (default: 10% or ₹4,000)
2. **Profit Drawdown**: Profit drops by configured percentage from peak (default: 40% from peak of 12.5% or ₹5,000)

### When Triggered

1. ⚠️ Warning sent (30 seconds before trigger)
2. 🔒 All open positions closed
3. 🚫 F&O segment deactivated automatically
4. 📱 Telegram confirmation sent
5. ⏸️ Monitoring stops (restart via `/monitor`)

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- Zerodha Kite account with API access
- Telegram account
- Ubuntu 20.04+ (for AWS deployment)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/grimmprog/kite-algo-killswitch.git
cd kite-algo-killswitch
```

2. **Create virtual environment**
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment**
```bash
cp .env.example .env
nano .env  # Edit with your credentials
```

5. **Set up TOTP**
- Get your TOTP secret from Google Authenticator or Authy
- Add it to `.env` as `KITE_TOTP_KEY`
- See [TOTP Setup Guide](TOTP_SETUP.md) for details

6. **Create Telegram bot**
- Message @BotFather on Telegram
- Create a new bot and get the token
- Get your chat ID from @userinfobot
- Add both to `.env`

7. **Test the setup**
```bash
python start_bot_with_monitor.py
```

8. **Send `/status` to your Telegram bot** to verify it's working

## 📱 Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and command list |
| `/status` | View bot status, positions, P&L, and monitoring state |
| `/monitor` | Start P&L monitoring |
| `/stopmonitor` | Stop P&L monitoring |
| `/segments` | Manage trading segments (activate/deactivate) |
| `/thresholds` | View current kill switch thresholds |
| `/setthreshold` | Guide to update thresholds |
| `/help` | Show all available commands |

## ☁️ AWS Deployment

### Quick Deployment (5 minutes)

1. **Prepare locally**
```bash
./pre_deploy_check.sh
```

2. **Upload to AWS**
```bash
scp -i your-key.pem -r kite-algo ubuntu@your-ec2-ip:~/
```

3. **Deploy on AWS**
```bash
ssh -i your-key.pem ubuntu@your-ec2-ip
cd ~/kite-algo
chmod +x aws_deploy.sh
./aws_deploy.sh
```

4. **Start the service**
```bash
sudo systemctl start kite-trading-bot
sudo systemctl enable kite-trading-bot
```

5. **Verify**
```bash
sudo systemctl status kite-trading-bot
tail -f logs/bot_monitor.log
```

### Detailed Documentation

- **[START_HERE_AWS.md](START_HERE_AWS.md)** - Complete AWS deployment guide
- **[AWS_QUICK_REFERENCE.md](AWS_QUICK_REFERENCE.md)** - Command reference
- **[DEPLOYMENT_ARCHITECTURE.md](DEPLOYMENT_ARCHITECTURE.md)** - System architecture

## 🔧 Configuration

### Environment Variables

Edit `.env` to configure:

```bash
# Zerodha Credentials
KITE_USER_ID=AB1234
KITE_PASSWORD=your_password
KITE_TOTP_KEY=your_totp_secret

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Trading Capital
CAPITAL=40000

# Kill Switch Thresholds (Percentage-based - Recommended)
LOSS_THRESHOLD_PERCENT=10          # 10% of capital
PROFIT_THRESHOLD_PERCENT=12.5      # 12.5% of capital
DRAWDOWN_THRESHOLD_PERCENT=40      # 40% drop from peak

# OR use fixed amounts (if percentage not set)
# LOSS_THRESHOLD=4000
# PROFIT_THRESHOLD=5000
# DRAWDOWN_THRESHOLD=2000
```

### Adjusting Thresholds

You can use either **percentage-based** (recommended) or **fixed amount** thresholds:

#### Percentage-Based (Scales with Capital)
```bash
# Recommended for flexibility
CAPITAL=40000
LOSS_THRESHOLD_PERCENT=10          # 10% of capital = ₹4,000
PROFIT_THRESHOLD_PERCENT=12.5      # 12.5% of capital = ₹5,000
DRAWDOWN_THRESHOLD_PERCENT=40      # 40% drop from peak profit
```

#### Fixed Amount
```bash
# Fixed rupee amounts
LOSS_THRESHOLD=4000                # Trigger at ₹4,000 loss
PROFIT_THRESHOLD=5000              # Track drawdown from ₹5,000 profit
DRAWDOWN_THRESHOLD=2000            # Trigger on ₹2,000 drop from peak
```

**Note:** If percentage is set, it takes priority over fixed amount.

#### View & Update via Telegram
- `/thresholds` - View current thresholds
- `/setthreshold` - Get instructions to update thresholds

## 📁 Project Structure

```
kite-algo/
├── start_bot_with_monitor.py    # Main startup script
├── telegram_bot.py               # Telegram bot interface
├── advanced_killswitch.py        # Kill switch logic
├── segment_automation.py         # Selenium automation for segments
├── auto_login.py                 # Daily auto-login script
├── config.py                     # Configuration loader
├── notifier.py                   # Notification helper
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment template
├── aws_deploy.sh                 # AWS deployment script
├── kite-trading-bot.service      # Systemd service file
└── docs/                         # Documentation
    ├── START_HERE_AWS.md
    ├── AWS_DEPLOYMENT_COMPLETE.md
    ├── AWS_QUICK_REFERENCE.md
    └── DEPLOYMENT_ARCHITECTURE.md
```

## 🔒 Security

- **Never commit `.env`** - Contains sensitive credentials
- **Use strong passwords** - For Zerodha account
- **Secure your server** - Use SSH keys, disable password auth
- **Restrict access** - AWS security groups, firewall rules
- **Regular updates** - Keep dependencies updated

## 📝 Logging

Logs are stored in the `logs/` directory:

- `bot_monitor.log` - Monitoring activity and triggers
- `bot_service.log` - Service output
- `bot_service_error.log` - Error messages
- `auto_login.log` - Daily login attempts

View logs:
```bash
tail -f logs/bot_monitor.log
```

## 🐛 Troubleshooting

### Service won't start
```bash
sudo journalctl -u kite-trading-bot -n 50
python start_bot_with_monitor.py  # Test manually
```

### Telegram not responding
```bash
# Check if bot is running
ps aux | grep telegram_bot

# Restart service
sudo systemctl restart kite-trading-bot
```

### Auto-login failing
```bash
# Check logs
tail -f logs/auto_login.log

# Test manually
python auto_login.py
```

### Chrome/Selenium issues
```bash
# Reinstall Chrome
sudo apt-get install --reinstall google-chrome-stable

# Test Selenium
python -c "from selenium import webdriver; print('OK')"
```

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [START_HERE_AWS.md](START_HERE_AWS.md) | AWS deployment quick start |
| [AWS_DEPLOYMENT_COMPLETE.md](AWS_DEPLOYMENT_COMPLETE.md) | Detailed deployment guide |
| [AWS_QUICK_REFERENCE.md](AWS_QUICK_REFERENCE.md) | Command reference card |
| [DEPLOYMENT_ARCHITECTURE.md](DEPLOYMENT_ARCHITECTURE.md) | System architecture |
| [DEPLOYMENT_CHECKLIST.txt](DEPLOYMENT_CHECKLIST.txt) | Deployment checklist |

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## ⚠️ Disclaimer

This software is for educational purposes only. Use at your own risk. The authors are not responsible for any financial losses incurred while using this software. Always test thoroughly with paper trading before using with real money.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Zerodha for the Kite Connect API
- python-telegram-bot library
- Selenium WebDriver
- All contributors and users

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/grimmprog/kite-algo-killswitch/issues)
- **Discussions**: [GitHub Discussions](https://github.com/grimmprog/kite-algo-killswitch/discussions)

## 🌟 Star History

If you find this project useful, please consider giving it a star ⭐

---

**Made with ❤️ for the trading community**
