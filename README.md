# Kite Algo Trading Bot

Complete automated trading system for NIFTY & BANKNIFTY options with Telegram control.

## 📋 Table of Contents
- [Setup](#setup)
- [Daily Routine](#daily-routine)
- [Command Reference](#command-reference)
- [Telegram Commands](#telegram-commands)
- [Strategy Details](#strategy-details)
- [Risk Management](#risk-management)

---

## 🚀 Setup

### Windows Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

**Note:** This includes NSEpy for FREE historical data from NSE (no subscription required!)

### 2. Configure Environment
Edit `.env` file with your credentials:
```
KITE_API_KEY=your_api_key
KITE_API_SECRET=your_api_secret
KITE_USER_ID=your_user_id
KITE_PASSWORD=your_password
KITE_TOTP_KEY=your_totp_secret_key
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 3. Setup TOTP (Required for Automation)

**TOTP enables:**
- ✅ Automated daily login (9:15 AM)
- ✅ Kill switch auto-deactivation of F&O segment
- ✅ Fully automated trading (no manual intervention)

**Quick Setup:**
```bash
# Interactive setup wizard (recommended)
python setup_totp_wizard.py

# Or test existing TOTP
python diagnose_totp.py

# Fix time sync issues
python fix_totp_time_sync.py
```

**📖 Detailed Guides:**
- `TOTP_COMPLETE_SOLUTION.md` - Quick reference & troubleshooting
- `TOTP_MULTI_DEVICE_GUIDE.md` - Use TOTP on multiple devices
- `TOTP_SETUP.md` - Detailed setup instructions

### 4. First Time Setup
```bash
# Generate access token
python login.py

# Test connection
python test_connection.py

# Test NSEpy integration (FREE data source)
python test_nsepy.py

# Test yfinance integration (FREE data source - recommended)
python test_yfinance.py

# Verify Telegram
python verify_telegram.py

# Verify strategy
python verify_strategy.py
```

---

### Ubuntu/Linux Setup (AWS/Cloud)

### 1. Run Setup Script
```bash
chmod +x ubuntu_setup.sh
./ubuntu_setup.sh
```

### 2. Configure Environment
```bash
nano .env
# Add your credentials
```

### 3. Make Scripts Executable
```bash
chmod +x *.sh
```

### 4. Test Installation
```bash
source venv/bin/activate
python test_connection.py
python verify_telegram.py
```

### 5. Start Bot
```bash
./start_all.sh
```

### 6. Check Status
```bash
./status.sh
```

For detailed AWS deployment, see [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md)

---

## 📅 Daily Routine

### Morning (Before Market Opens)
```bash
# 1. Generate new access token (expires daily)
python login.py

# 2. Test connection
python test_connection.py
```

### Start Trading
```bash
# Option 1: Start with pre-flight checks
python start_bot.py

# Option 2: Direct start
python main.py
```

---

## 💻 Command Reference

### Authentication & Setup

| Command | Description | Usage |
|---------|-------------|-------|
| `python login.py` | Generate daily access token | Run every morning |
| `python test_connection.py` | Verify Kite API connection | After login |
| `python test_yfinance.py` | Test yfinance data source (FREE) | One-time setup |
| `python test_nsepy.py` | Test NSEpy data source (FREE backup) | One-time setup |
| `python verify_telegram.py` | Test Telegram notifications | One-time setup |
| `python verify_strategy.py` | Test strategy logic | One-time setup |
| `python get_chat_id.py` | Get Telegram chat ID | One-time setup |

### Trading Operations

| Command | Description | Usage |
|---------|-------------|-------|
| `python main.py` | Start automated trading bot | Daily trading |
| `python start_bot.py` | Start with pre-flight checks | Recommended daily start |
| `python manual_order.py` | Place manual order with GTT | Manual trading |
| `python position_monitor.py` | Active position monitoring | After placing order |
| `python kill_switch.py` | Risk management monitor | Run alongside trading |

### Monitoring & Control

| Command | Description | Options |
|---------|-------------|---------|
| `python kill_switch.py` | Advanced risk management | 1: Monitor, 2: Check P&L, 3: Close all |
| `python position_monitor.py` | Real-time position tracking | Enter symbol & prices |

---

## 📱 Telegram Commands

### Basic Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Show welcome & available commands | `/start` |
| `/help` | Display help message | `/help` |
| `/status` | Quick P&L status with buttons | `/status` |
| `/pnl` | Detailed P&L breakdown | `/pnl` |
| `/positions` | View all open positions | `/positions` |
| `/close` | Close all positions (with confirmation) | `/close` |

### Interactive Buttons

When you send `/status`, you get interactive buttons:
- **📊 Detailed** - View detailed P&L
- **📍 Positions** - Show open positions
- **🚨 Close All** - Emergency close all positions

### Automated Notifications

The bot automatically sends Telegram messages for:
- ✅ Trade signals found (requires approval)
- 🎯 Target hit
- 🛑 Stop loss hit
- ⚠️ Profit > 10% of capital warning
- 🚨 Kill switch activation
- ❌ Errors and failures

---

## 📊 Strategy Details

### Data Source
**Yahoo Finance (yfinance)** - FREE and reliable historical data
- No subscription required
- No API key needed
- Daily OHLC data for NIFTY 50 and NIFTY BANK
- Backup: NSEpy (also free)
- See [FREE_DATA_SOURCES.md](FREE_DATA_SOURCES.md) for details

### Strategy Name
**Trend Pullback Continuation**

### Instruments
- NIFTY 50 (PE options)
- NIFTY BANK (PE options)

### Trading Hours
- **Entry Window:** 9:25 AM - 11:15 AM
- **Auto Square-off:** 3:15 PM

### Entry Conditions
1. **Trend:** Bearish (Price < VWAP, EMA 20 sloping down, MACD < 0)
2. **Impulse:** Large body candle with high volume
3. **Pullback:** Small body candles near 20 EMA
4. **Trigger:** Break of pullback low with bearish close
5. **Confidence:** Score ≥ 70%

### Exit Conditions
- **Target:** 1:1 Risk-Reward (50% booking)
- **Stop Loss:** High of pullback candle
- **Auto Exit:** Price closes above 20 EMA or touches VWAP

---

## 🛡️ Risk Management

### Capital Settings
```
Capital: ₹40,000
Max Daily Loss: ₹3,000
Max Trades/Day: 2
Max Active Trades: 1
Confidence Threshold: 70%
```

### Kill Switch Rules

| Rule | Threshold | Action |
|------|-----------|--------|
| **Max Loss** | Loss > ₹4,000 | Close all positions |
| **Profit Drawdown** | Profit ≥ ₹5,000 then drops ₹2,000 | Close all positions |
| **Profit Warning** | Profit > 10% of capital (₹4,000) | Send Telegram alert |

### Lot Sizes
- **NIFTY:** 65 quantity per lot
- **BANKNIFTY:** 15 quantity per lot

---

## 📁 File Structure

```
kite-algo/
├── .env                      # Environment variables (credentials)
├── config.py                 # Configuration settings
├── connect.py                # Kite API connection
├── login.py                  # Generate access token
├── test_connection.py        # Test Kite connection
├── test_yfinance.py         # Test yfinance data source (FREE)
├── test_nsepy.py            # Test NSEpy data source (FREE backup)
├── get_chat_id.py           # Get Telegram chat ID
│
├── main.py                   # Main trading bot
├── start_bot.py             # Bot with pre-flight checks
├── scanner.py               # Market scanner
├── strategy.py              # Trading strategy logic
├── indicators.py            # Technical indicators
├── confidence.py            # Confidence scoring
│
├── execution.py             # Order execution
├── manual_order.py          # Manual order placement
├── position_monitor.py      # Active position monitoring
├── exit_manager.py          # Exit management
│
├── risk.py                  # Risk management
├── kill_switch.py           # Advanced risk control
│
├── notifier.py              # Telegram notifications
├── telegram_bot.py          # Telegram bot interface
├── verify_telegram.py       # Test Telegram
├── verify_strategy.py       # Test strategy
│
├── journal.py               # Trade journaling
├── broker.py                # Broker interface
├── server.py                # Web server (optional)
│
├── access_token.txt         # Saved access token (auto-generated)
├── logs/                    # Log files
│   └── bot.log
└── templates/               # Web templates (optional)
```

---

## 🔧 Configuration Files

### config.py
Main configuration for:
- API credentials
- Trading hours
- Risk parameters
- Strategy settings
- Instrument details

### .env
Sensitive credentials:
- Kite API key & secret
- Telegram bot token & chat ID
- User credentials

---

## 🎯 Quick Start Guide

### 1. Morning Setup (5 minutes)
```bash
# Generate token
python login.py

# Start bot with checks
python start_bot.py
```

### 2. During Trading
- Bot scans every minute
- Sends Telegram alerts for trades
- Approve/reject via Telegram buttons
- Monitor via `/status` command

### 3. Risk Monitoring
```bash
# In separate terminal
python kill_switch.py
# Select option 1 (Monitor)
```

### 4. Manual Trading
```bash
# Place manual order
python manual_order.py

# Monitor position actively
python position_monitor.py
```

---

## 📞 Support & Troubleshooting

### Common Issues

**Access Token Expired**
```bash
python login.py
```

**Telegram Not Working**
```bash
python verify_telegram.py
python get_chat_id.py
```

**Symbol Not Found**
- Check symbol format in config.py
- Verify instrument list with Kite

**Multiple Bot Instances**
- Only run one bot at a time
- Kill other processes before starting new one

---

## 📈 Performance Tracking

### View Logs
```bash
# View bot logs
type logs\bot.log

# View last 50 lines
powershell -command "Get-Content logs\bot.log -Tail 50"
```

### Check Today's P&L
```bash
python kill_switch.py
# Select option 2
```

Or via Telegram:
```
/pnl
```

---

## ⚠️ Important Notes

1. **Access Token:** Expires daily - run `login.py` every morning
2. **Paper Trading:** Test with small positions first
3. **Monitor Actively:** Don't leave completely unattended initially
4. **Respect Stop Loss:** Bot manages exits automatically
5. **Kill Switch:** Always run alongside trading for protection
6. **Telegram:** Keep bot running for notifications
7. **Market Hours:** Bot only trades during configured hours
8. **Risk First:** Never risk more than you can afford to lose

---

## 📝 License

Private use only. Not for distribution.

---

## 🎉 Success Checklist

- [ ] Dependencies installed (including yfinance)
- [ ] .env configured
- [ ] Access token generated
- [ ] yfinance tested (FREE data source - recommended)
- [ ] NSEpy tested (FREE backup data source)
- [ ] Telegram bot tested
- [ ] Strategy verified
- [ ] First test trade successful
- [ ] Kill switch tested
- [ ] Telegram commands working
- [ ] Position monitor tested
- [ ] Logs directory created

---

**Happy Trading! 🚀📈**

For questions or issues, check logs or send `/help` to your Telegram bot.
