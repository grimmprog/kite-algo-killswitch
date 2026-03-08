# Telegram Bot Troubleshooting - Can't Find Options/Buttons

## Problem
You can't see the buttons/options when using Telegram commands like `/segments` or `/status`.

## Most Common Causes

### 1. Wrong Bot Running ❌
You might be running `notifier.py` (old bot) instead of `telegram_bot.py` (new bot with buttons).

**Solution:**
```bash
# Check which bot is running
python check_bot_status.py

# Restart with correct bot
restart_telegram_bot.bat
```

### 2. Bot Not Restarted After Updates ❌
The bot needs to be restarted to load the new button code.

**Solution:**
```bash
# Stop the bot (Ctrl+C in terminal)
# Then restart
restart_telegram_bot.bat
```

### 3. Multiple Bot Instances Running ❌
Multiple bots can cause conflicts.

**Solution:**
```bash
# Check status
python check_bot_status.py

# Kill all Python processes
taskkill /IM python.exe /F

# Restart bot
restart_telegram_bot.bat
```

## Quick Fix Steps

### Step 1: Check Bot Status
```bash
cd kite-algo
python check_bot_status.py
```

This will tell you:
- Which bot is running (should be `telegram_bot.py`)
- If multiple instances are running
- What to do next

### Step 2: Restart Bot
```bash
restart_telegram_bot.bat
```

This will:
- Stop any running bots
- Start `telegram_bot.py` (the correct one)
- Show you available commands

### Step 3: Test in Telegram

Send these commands to test:

1. **Test basic command:**
   ```
   /start
   ```
   Should show a list of all commands.

2. **Test buttons:**
   ```
   /status
   ```
   Should show buttons like:
   - 📊 Detailed P&L
   - 📍 Positions
   - 🚨 Close All
   - ⚡ Kill Switch

3. **Test segments:**
   ```
   /segments
   ```
   Should show buttons like:
   - 🔒 Deactivate Segments
   - ✅ Activate Segments
   - 🔒 Deactivate ALL
   - ✅ Activate ALL

## If Buttons Still Don't Show

### Check 1: Telegram App Version
Make sure your Telegram app is updated. Old versions may not support inline buttons.

**Solution:**
- Update Telegram app on your phone/desktop
- Try using Telegram Web: https://web.telegram.org

### Check 2: Bot Token
Verify the bot token is correct in `.env` file.

**Check:**
```bash
# Open .env file
notepad .env

# Look for:
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

### Check 3: Bot Permissions
The bot needs permission to send messages with buttons.

**Solution:**
1. Open Telegram
2. Find your bot
3. Send `/start` to the bot
4. Make sure you're not blocking the bot

## Expected Behavior

### `/status` Command
Should show:
```
🟢 QUICK STATUS

Day P&L: ₹0.00 (+0.00%)
Open Positions: 0
Time: 14:30:45

[📊 Detailed P&L] [📍 Positions]
[🚨 Close All] [⚡ Kill Switch]
```

### `/segments` Command
Should show:
```
🔒 SEGMENT MANAGEMENT

Choose an action:

[🔒 Deactivate Segments]
[✅ Activate Segments]
[🔒 Deactivate ALL]
[✅ Activate ALL]
```

## Still Not Working?

### Option 1: Check Console Output
Look at the terminal where the bot is running. Check for errors like:
- `AttributeError: 'TradingBot' object has no attribute 'segments_command'`
- `ImportError: cannot import name...`
- `ConnectionError: ...`

### Option 2: Test with Simple Command
Try a simple command first:
```
/help
```

If this works but `/segments` doesn't, there might be an issue with the segments command specifically.

### Option 3: Check Logs
```bash
# Look for error messages
type logs\telegram_bot.log
```

### Option 4: Reinstall Dependencies
```bash
pip install --upgrade python-telegram-bot
```

## Manual Test

If automated scripts don't work, manually test:

1. **Stop all bots:**
   ```bash
   taskkill /IM python.exe /F
   ```

2. **Start telegram_bot.py directly:**
   ```bash
   cd kite-algo
   python telegram_bot.py
   ```

3. **Watch console output** for errors

4. **Test in Telegram:**
   - Send `/start`
   - Send `/segments`
   - Check if buttons appear

## Common Error Messages

### "No module named 'telegram'"
```bash
pip install python-telegram-bot
```

### "AttributeError: 'TradingBot' object has no attribute 'segments_command'"
The bot file is outdated. Make sure you're using the latest `telegram_bot.py`.

### "Conflict: terminated by other getUpdates request"
Multiple bot instances are running. Kill all and restart:
```bash
taskkill /IM python.exe /F
restart_telegram_bot.bat
```

## Files to Check

1. **telegram_bot.py** - Main bot file (should have segments_command)
2. **.env** - Bot token and chat ID
3. **config.py** - Configuration settings

## Quick Reference

| Command | Expected Result |
|---------|----------------|
| `/start` | List of all commands |
| `/help` | Same as /start |
| `/status` | Status with 4 buttons |
| `/segments` | Segment menu with 4 buttons |
| `/killswitch` | Kill switch status |

## Need More Help?

1. Run diagnostic: `python check_bot_status.py`
2. Check console output for errors
3. Verify `.env` file has correct tokens
4. Make sure only ONE bot instance is running
5. Restart bot: `restart_telegram_bot.bat`

---

**Quick Fix:** Run `restart_telegram_bot.bat` and try `/segments` again!
