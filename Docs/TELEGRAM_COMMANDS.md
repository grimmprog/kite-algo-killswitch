# Telegram Bot Commands - Complete Guide

## Quick Reference

| Command | Shortcut | Description |
|---------|----------|-------------|
| `/start` | - | Welcome message & command list |
| `/help` | - | Show all commands |
| `/status` | - | Quick P&L with interactive buttons ⭐ |
| `/pnl` | - | Detailed P&L breakdown |
| `/positions` | `/pos` | View open positions |
| `/close` | `/closeall` | Close all positions |
| `/killswitch` | `/ks` | Kill switch status & activation |
| `/capital` | - | Check available capital |
| `/risk` | - | View risk metrics |
| `/scan` | - | Manual scan for setups |
| `/consolidation` | `/cons` | Check consolidation setups |
| `/paper` | - | Paper trading status |
| `/papertrades` | - | Paper trade history |
| `/orders` | - | Today's orders |
| `/history` | - | Trade history |
| `/bot` | - | Bot system status |
| `/time` | - | Current time & market status |

---

## 📊 Status & P&L Commands

### `/status` ⭐ MOST USED
**Quick P&L status with interactive buttons**

**Output:**
```
🟢 QUICK STATUS

Day P&L: ₹+2,500.00 (+6.25%)
Open Positions: 2
Time: 14:30:15

[📊 Detailed P&L] [📍 Positions]
[🚨 Close All]
```

**Interactive Buttons:**
- **📊 Detailed P&L** - Shows full breakdown
- **📍 Positions** - Lists all open positions
- **🚨 Close All** - Emergency close (with confirmation)

**When to use:** Check status anytime during trading

---

### `/pnl`
**Detailed P&L breakdown with risk metrics**

**Output:**
```
🟢 DETAILED P&L REPORT

📅 Day P&L: ₹+2,500.00 (+6.25%)
💼 Net P&L: ₹+2,500.00
💰 Capital: ₹40,000
📊 Open Positions: 2
🕐 Time: 23-Jan-2026 14:30:15

✅ Profit: 6.25%
```

**Shows:**
- Day P&L (today's profit/loss)
- Net P&L (overall)
- Capital available
- Open position count
- Profit/loss percentage
- Kill switch warnings if applicable

**When to use:** Detailed analysis, end of day review

---

### `/positions` or `/pos`
**View all open positions**

**Output:**
```
📊 OPEN POSITIONS (2)

1. NIFTY 25200 PE
   🟢 LONG | Qty: 65
   Avg: ₹86.70 | LTP: ₹120.50
   ✅ P&L: ₹2,197.00

2. NIFTY 25100 CE
   🔴 SHORT | Qty: 65
   Avg: ₹45.20 | LTP: ₹40.50
   ✅ P&L: ₹305.50
```

**Shows for each position:**
- Symbol & strike
- Long/Short
- Quantity
- Average price
- Last traded price (LTP)
- Current P&L

**When to use:** Monitor individual positions

---

## 🎯 Trading Commands

### `/close` or `/closeall`
**Close all open positions**

**Flow:**
1. Shows confirmation with current P&L
2. Requires button click to confirm
3. Closes all positions at market price
4. Shows final P&L

**Output:**
```
⚠️ CLOSE ALL POSITIONS?

Current Day P&L: ₹+2,500.00
Open Positions: 2

This will close all positions immediately!

[✅ YES, CLOSE ALL] [❌ CANCEL]
```

**After execution:**
```
✅ POSITIONS CLOSED

Closed: 2/2
Final Day P&L: ₹+2,502.50
Time: 14:35:20
```

**When to use:** 
- Emergency exit
- End of day square-off
- Risk management

---

### `/killswitch` or `/ks`
**Kill switch status and activation**

**Output (Safe):**
```
🚨 KILL SWITCH STATUS

🟢 SAFE
P&L: ₹+1,200.00

Open Positions: 2
```

**Output (Warning):**
```
🚨 KILL SWITCH STATUS

🟡 MONITORING
Loss: ₹-2,500.00
Remaining: ₹1,500.00 until activation

Open Positions: 2

[🚨 ACTIVATE KILL SWITCH]
```

**Output (Activated):**
```
🚨 KILL SWITCH STATUS

🔴 ACTIVATED - Max loss exceeded!
Loss: ₹-4,200.00 (Limit: ₹4,000)

Open Positions: 0
```

**Thresholds:**
- Max Loss: ₹4,000 (10% of ₹40,000 capital)
- Profit Warning: ₹4,000 (10% of capital)
- Profit Protection: ≥₹5,000 then drops ₹2,000

**When to use:** 
- Check risk status
- Manual kill switch activation
- Monitor loss limits

---

## 💰 Capital & Risk Commands

### `/capital`
**Check available capital and margins**

**Output:**
```
💰 CAPITAL STATUS

Available: ₹35,500.00
Used: ₹4,500.00
Total: ₹40,000.00

Configured Capital: ₹40,000
```

**Shows:**
- Available balance
- Used margin
- Total capital
- Configured trading capital

**When to use:** Before placing new trades

---

### `/risk`
**View risk metrics and exposure**

**Output:**
```
⚠️ RISK METRICS

Day P&L: ₹-1,500.00 (-3.75%)
Max Loss: ₹4,000 (10.0%)
Open Positions: 2

Risk Used: 37.5%
```

**Shows:**
- Current P&L
- Maximum allowed loss
- Risk percentage used
- Open position count

**When to use:** Risk assessment, position sizing

---

## 🔍 Scanning Commands

### `/scan`
**Manual scan for trading setups**

**Output:**
```
🔍 Scanning for setups...

This will trigger the scanner manually.
```

**Triggers:**
- Trend pullback scanner
- Consolidation breakout scanner
- Sends alerts if setups found

**When to use:** 
- Check for opportunities
- Manual strategy trigger

---

### `/consolidation` or `/cons`
**Check for consolidation breakout setups**

**Output:**
```
📊 Consolidation Scanner

Checking for tight range consolidations...
This feature scans for 20-30 min consolidations
with < 15% range for breakout opportunities.
```

**Looks for:**
- 20-30 minute consolidations
- < 15% price range
- Multiple boundary tests
- Breakout potential

**When to use:** 
- Find high RR setups
- Afternoon trading opportunities

---

## 📝 Paper Trading Commands

### `/paper`
**Paper trading account status**

**Output:**
```
📝 PAPER TRADING STATUS

Starting: ₹40,000.00
Current: ₹46,500.00
P&L: ₹+6,500.00 (+16.25%)

Total Trades: 15
Open Positions: 1
```

**Shows:**
- Starting capital
- Current capital
- Total P&L
- Number of trades
- Open positions

**When to use:** Track paper trading performance

---

### `/papertrades`
**View paper trade history**

**Output:**
```
📝 RECENT PAPER TRADES (Last 5)

✅ #11: NIFTY 25200 PE
   P&L: ₹+2,635.75 | TARGET

✅ #12: NIFTY 25100 CE
   P&L: ₹+1,820.00 | MANUAL

❌ #13: NIFTY 25300 PE
   P&L: ₹-390.00 | STOP_LOSS

✅ #14: NIFTY 25150 PE
   P&L: ₹+3,250.00 | TARGET

✅ #15: NIFTY 25200 PE
   P&L: ₹+6,756.75 | TARGET
```

**Shows:**
- Trade ID
- Symbol & strike
- P&L
- Exit reason

**When to use:** Review paper trading performance

---

## 📋 Orders & History Commands

### `/orders`
**View today's orders**

**Output:**
```
📋 TODAY'S ORDERS (5)

✅ NIFTY 25200 PE
   BUY 65 @ ₹86.70
   Status: COMPLETE

✅ NIFTY 25200 PE
   SELL 65 @ ₹120.50
   Status: COMPLETE

⏳ NIFTY 25100 CE
   BUY 65 @ ₹45.00
   Status: OPEN
```

**Shows:**
- Order status (✅ Complete, ⏳ Open, ❌ Rejected)
- Symbol
- Buy/Sell
- Quantity & Price
- Current status

**When to use:** Track order execution

---

### `/history`
**Trade history overview**

**Output:**
```
📊 TRADE HISTORY

Use /orders for today's orders
Use /pnl for current P&L
Use /papertrades for paper trading history
```

**When to use:** Navigate to specific history

---

## ⚙️ System Commands

### `/bot`
**Bot system status**

**Output:**
```
🤖 BOT STATUS

Status: ✅ Running
Platform: Windows
CPU: 15%
Memory: 45%
Time: 14:30:15
```

**Shows:**
- Bot running status
- Operating system
- CPU usage
- Memory usage
- Current time

**When to use:** Check if bot is running properly

---

### `/time`
**Current time and market status**

**Output (Market Open):**
```
🕐 TIME

Current: 23-Jan-2026 14:30:15
Market: 🟢 OPEN
```

**Output (Market Closed):**
```
🕐 TIME

Current: 23-Jan-2026 08:30:15
Market: 🔴 CLOSED
Opens in: 45 minutes
```

**Shows:**
- Current date & time
- Market status (Open/Closed)
- Time until market opens (if closed)

**When to use:** Check market hours

---

## 🎮 Interactive Buttons

### Status Command Buttons

When you use `/status`, you get interactive buttons:

**📊 Detailed P&L**
- Click to see full P&L breakdown
- Same as `/pnl` command

**📍 Positions**
- Click to see all open positions
- Same as `/positions` command

**🚨 Close All**
- Click to initiate close all
- Requires confirmation

### Close All Confirmation

**✅ YES, CLOSE ALL**
- Confirms and executes close all
- Closes all positions immediately

**❌ CANCEL**
- Cancels the close all operation
- No positions closed

### Kill Switch Activation

**🚨 ACTIVATE KILL SWITCH**
- Manually activates kill switch
- Closes all positions
- Deactivates F&O segment (if configured)

---

## 📱 Usage Examples

### Morning Routine
```
/time          # Check market status
/capital       # Check available capital
/status        # Quick status check
```

### During Trading
```
/status        # Quick P&L check (every 30 min)
/pos           # Check positions
/risk          # Monitor risk
```

### Emergency
```
/ks            # Check kill switch status
/close         # Close all positions
```

### End of Day
```
/pnl           # Detailed P&L
/orders        # Review orders
/paper         # Check paper trading
```

---

## 🔔 Notifications

The bot automatically sends notifications for:

### Trade Signals
```
🔥 SIGNAL FOUND!

NIFTY 25200 PE
Entry: ₹86.70
Stop: ₹81.20
Target: ₹120.00

[APPROVE] [REJECT]
```

### Position Updates
```
✅ TARGET HIT!

NIFTY 25200 PE
Entry: ₹86.70
Exit: ₹120.50
P&L: ₹+2,197.00 (+39.5%)
```

### Kill Switch Alerts
```
🚨 KILL SWITCH ACTIVATED!

Reason: Max loss exceeded
Loss: ₹-4,200.00
All positions closed
```

### Paper Trade Updates
```
📝 PAPER TRADE ENTERED

Trade #15
Symbol: NIFTY 25200 PE
Entry: ₹86.70
Stop: ₹81.20
Target: ₹120.00
```

---

## 💡 Pro Tips

### 1. Use Shortcuts
- `/pos` instead of `/positions`
- `/ks` instead of `/killswitch`
- `/cons` instead of `/consolidation`

### 2. Interactive Buttons
- Use `/status` for quick access to all actions
- Buttons are faster than typing commands

### 3. Set Up Alerts
- Enable Telegram notifications
- Get instant updates on trades
- Never miss important events

### 4. Regular Checks
- `/status` every 30 minutes during trading
- `/risk` before placing new trades
- `/pnl` at end of day

### 5. Emergency Protocol
1. `/ks` - Check kill switch
2. `/close` - Close all if needed
3. `/pnl` - Confirm final P&L

---

## 🔧 Setup

### 1. Get Bot Token
```
1. Message @BotFather on Telegram
2. Create new bot: /newbot
3. Copy bot token
4. Add to .env file: TELEGRAM_BOT_TOKEN=your_token
```

### 2. Get Chat ID
```bash
python get_chat_id.py
```

### 3. Start Bot
```bash
python telegram_bot.py
```

### 4. Test
```
Send /start to your bot
Should receive welcome message
```

---

## 🐛 Troubleshooting

### Bot Not Responding
```bash
# Check if bot is running
python telegram_bot.py

# Check logs
type logs\bot.log
```

### Commands Not Working
```
1. Check bot is running
2. Verify chat ID in .env
3. Test with /start command
4. Check internet connection
```

### No Notifications
```
1. Verify TELEGRAM_CHAT_ID in .env
2. Test with /status command
3. Check bot permissions
```

---

## 📚 Related Files

- **telegram_bot.py** - Main bot code
- **notifier.py** - Notification functions
- **.env** - Bot token & chat ID
- **telegram_commands.txt** - Command list
- **TELEGRAM_SETUP.md** - Setup guide

---

## 🎯 Command Priority

**High Priority (Use Often):**
- `/status` - Quick checks
- `/pos` - Monitor positions
- `/close` - Emergency exit

**Medium Priority (Use Daily):**
- `/pnl` - End of day review
- `/risk` - Before new trades
- `/orders` - Track execution

**Low Priority (Use As Needed):**
- `/scan` - Manual scanning
- `/paper` - Paper trading review
- `/bot` - System check

---

**Master these commands and control your trading from anywhere via Telegram!** 📱🚀
