# Telegram Bot - Quick Start (2 Minutes)

## Setup Commands

```bash
# 1. Get chat ID
python get_chat_id.py

# 2. Register commands
python register_telegram_commands.py

# 3. Start bot
python telegram_bot.py
```

## Test in Telegram

```
/start    # Welcome message
/status   # Quick P&L (with buttons)
/help     # All commands
```

## All Commands (21 Total)

### Most Used ⭐
- `/status` - Quick P&L with buttons
- `/pos` - View positions
- `/close` - Close all positions
- `/ks` - Kill switch

### Status & P&L
- `/pnl` - Detailed P&L
- `/capital` - Check capital
- `/risk` - Risk metrics

### Trading
- `/orders` - Today's orders
- `/history` - Trade history

### Scanning
- `/scan` - Manual scan
- `/cons` - Consolidation scanner

### Paper Trading
- `/paper` - Paper status
- `/papertrades` - Paper history

### System
- `/bot` - Bot status
- `/time` - Current time
- `/help` - All commands

## Interactive Buttons

Use `/status` to get buttons for:
- 📊 Detailed P&L
- 📍 Positions
- 🚨 Close All

## Shortcuts

- `/pos` = `/positions`
- `/ks` = `/killswitch`
- `/cons` = `/consolidation`
- `/closeall` = `/close`

## Troubleshooting

**Bot not responding?**
```bash
# Check if running
python telegram_bot.py

# Get chat ID again
python get_chat_id.py
```

**Commands not in menu?**
```bash
# Re-register
python register_telegram_commands.py
```

## Files

- **telegram_bot.py** - Main bot
- **TELEGRAM_COMMANDS.md** - Full guide
- **TELEGRAM_SETUP_COMPLETE.md** - Detailed setup
- **register_telegram_commands.py** - Command registration

---

**That's it! Your bot is ready with all 21 commands.** 🚀

Type `/` in Telegram to see the command menu!
