# Telegram Bot Command Shortcuts Setup

## How to Add Command Menu to Your Bot

### Step 1: Open BotFather
1. Open Telegram
2. Search for `@BotFather`
3. Start a chat with BotFather

### Step 2: Set Commands
1. Send `/setcommands` to BotFather
2. Select your bot from the list
3. Copy and paste the following commands:

```
start - Show welcome and all commands
help - Display help message
status - Quick P&L status with buttons
pnl - Detailed P&L breakdown
positions - View all open positions
orders - View today's order history
capital - Capital and risk information
killswitch - Check kill switch status
monitor - Position monitoring info
close - Close all positions
```

### Step 3: Confirm
- BotFather will confirm: "Success! Command list updated."
- Now when you open your bot, you'll see a menu button (☰) next to the message input
- Click it to see all available commands

### Step 4: Test
1. Open your bot in Telegram
2. Click the menu button (☰) at the bottom left
3. You should see all commands listed
4. Click any command to execute it

---

## Alternative: Use Inline Keyboard (Already Implemented)

Your bot already has inline keyboard buttons! When you send `/status`, you get:
- 📊 Detailed P&L
- 📍 Positions
- 📋 Orders
- 💰 Capital
- 🚨 Close All

These are clickable buttons that appear directly in the message.

---

## Quick Access Commands

### Most Used Commands:
- `/status` - Your main dashboard (use this most often)
- `/pnl` - When you want detailed breakdown
- `/close` - Emergency exit

### Monitoring:
- `/positions` - Check what's open
- `/orders` - See order history
- `/killswitch` - Risk status

### Information:
- `/capital` - Risk limits
- `/monitor` - Monitoring guide
- `/help` - Command list

---

## Pro Tip: Create Telegram Shortcuts

On mobile, you can:
1. Long press on a command in chat
2. Select "Copy"
3. Save frequently used commands in your phone's notes
4. Or use Telegram's "Saved Messages" to store command templates

---

## Command Aliases (Optional)

If you want shorter commands, you can add aliases. Edit `notifier.py` and add:

```python
dp.add_handler(CommandHandler("s", self.status_command))  # /s for status
dp.add_handler(CommandHandler("p", self.positions_command))  # /p for positions
dp.add_handler(CommandHandler("c", self.close_command))  # /c for close
```

Then update BotFather with:
```
s - Quick status (alias)
p - Positions (alias)
c - Close all (alias)
```

---

## Visual Guide

### Before Setting Commands:
```
[Type a message...]
```

### After Setting Commands:
```
☰ [Type a message...]
  ↑
  Click here to see command menu
```

### Command Menu Will Show:
```
/start - Show welcome and all commands
/status - Quick P&L status with buttons
/pnl - Detailed P&L breakdown
/positions - View all open positions
...
```

---

## Troubleshooting

**Menu button not showing?**
- Make sure you completed the BotFather setup
- Restart your Telegram app
- Clear Telegram cache

**Commands not working?**
- Make sure the bot is running (`test_telegram_commands.py`)
- Check if bot process is active
- Verify bot token in `.env` file

**Want to remove commands?**
- Send `/deletecommands` to BotFather
- Select your bot

---

## Summary

1. **Quick Setup:** Send `/setcommands` to @BotFather
2. **Paste Commands:** Copy the command list above
3. **Done:** Menu button (☰) appears in your bot
4. **Use:** Click menu to see all commands

This makes your bot much easier to use - no need to remember or type commands!
