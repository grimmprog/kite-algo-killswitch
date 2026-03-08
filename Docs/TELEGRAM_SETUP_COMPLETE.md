# Complete Telegram Bot Setup Guide

## Quick Setup (5 Minutes)

### Step 1: Create Bot
```
1. Open Telegram
2. Search for @BotFather
3. Send: /newbot
4. Choose bot name (e.g., "My Trading Bot")
5. Choose username (e.g., "mytradingbot123_bot")
6. Copy the bot token
```

### Step 2: Add Token to .env
```bash
# Edit .env file
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```

### Step 3: Get Chat ID
```bash
# Run this script
python get_chat_id.py

# Follow instructions:
# 1. Send /start to your bot
# 2. Script will show your chat ID
# 3. Copy the chat ID
```

### Step 4: Add Chat ID to .env
```bash
# Edit .env file
TELEGRAM_CHAT_ID=123456789
```

### Step 5: Register Commands
```bash
# Automatically register all commands
python register_telegram_commands.py
```

### Step 6: Start Bot
```bash
# Start the bot
python telegram_bot.py
```

### Step 7: Test
```
1. Open Telegram
2. Find your bot
3. Send: /start
4. You should see welcome message
5. Try: /status
```

---

## Detailed Setup

### 1. Create Telegram Bot

**Open Telegram and message @BotFather:**

```
You: /newbot

BotFather: Alright, a new bot. How are we going to call it?
           Please choose a name for your bot.

You: My Trading Bot

BotFather: Good. Now let's choose a username for your bot.
           It must end in `bot`. Like this, for example:
           TetrisBot or tetris_bot.

You: mytradingbot123_bot

BotFather: Done! Congratulations on your new bot.
           You will find it at t.me/mytradingbot123_bot
           
           Use this token to access the HTTP API:
           1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
           
           Keep your token secure and store it safely,
           it can be used by anyone to control your bot.
```

**Copy the token!**

---

### 2. Configure .env File

Edit `kite-algo/.env`:

```bash
# Telegram Bot Credentials
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=your_chat_id_here  # Will get this in next step
```

---

### 3. Get Your Chat ID

**Method 1: Using get_chat_id.py (Recommended)**

```bash
# Run the script
python get_chat_id.py

# Output:
# ============================================================
# TELEGRAM CHAT ID FINDER
# ============================================================
# 
# Bot Token: 1234567890:ABC...
# 
# Instructions:
# 1. Open Telegram
# 2. Search for your bot: @mytradingbot123_bot
# 3. Send /start to the bot
# 4. Come back here and press Enter
# 
# Waiting for message...

# After you send /start:
# ✅ Chat ID found: 123456789
# 
# Add this to your .env file:
# TELEGRAM_CHAT_ID=123456789
```

**Method 2: Manual (Alternative)**

```
1. Send /start to your bot
2. Open browser
3. Go to: https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
4. Look for "chat":{"id":123456789}
5. Copy the ID number
```

---

### 4. Update .env with Chat ID

```bash
# Edit .env file
TELEGRAM_CHAT_ID=123456789  # Your actual chat ID
```

---

### 5. Register Bot Commands

**Automatic Registration (Recommended):**

```bash
python register_telegram_commands.py
```

**Output:**
```
======================================================================
TELEGRAM BOT COMMAND REGISTRATION
======================================================================

🔄 Attempting automatic registration...
✅ Commands registered successfully!

📝 Registered 21 commands:
   /start          - 🏠 Welcome & command list
   /help           - ❓ Show all commands
   /status         - 📊 Quick P&L status (with buttons)
   /pnl            - 💰 Detailed P&L breakdown
   /positions      - 📍 View open positions
   ... (and more)

💡 Commands will now appear in Telegram menu!
   (Tap the / button in chat to see them)

✅ Done! Your bot commands are ready to use.
```

**Manual Registration (If Automatic Fails):**

```
1. Message @BotFather
2. Send: /setcommands
3. Select your bot
4. Copy and paste the command list from register_telegram_commands.py output
```

---

### 6. Start the Bot

**Option 1: Standalone Bot**

```bash
# Run bot in foreground
python telegram_bot.py

# Output:
# INFO:__main__:Starting Telegram Trading Bot...
# INFO:__main__:Bot is running. Press Ctrl+C to stop.
```

**Option 2: With Trading Bot**

```bash
# Start main trading bot (includes Telegram)
python start_bot.py
```

**Option 3: Background (Linux/Mac)**

```bash
# Run in background
nohup python telegram_bot.py > telegram_bot.log 2>&1 &

# Check if running
ps aux | grep telegram_bot.py

# Stop
pkill -f telegram_bot.py
```

**Option 4: Background (Windows)**

```powershell
# Run in background
Start-Process python -ArgumentList "telegram_bot.py" -WindowStyle Hidden

# Or use Task Scheduler for automatic startup
```

---

### 7. Test the Bot

**Basic Test:**

```
1. Open Telegram
2. Find your bot
3. Send: /start
```

**Expected Response:**
```
🤖 Kite Algo Trading Bot

📊 Status & P&L
/status - Quick P&L status with buttons
/pnl - Detailed P&L breakdown
/positions or /pos - View open positions
...
```

**Test Commands:**

```
/status     # Should show current P&L
/time       # Should show current time
/bot        # Should show bot status
/help       # Should show all commands
```

---

## Command Menu Setup

After registration, commands appear in Telegram:

**To see commands:**
1. Open chat with your bot
2. Tap the **/** button (bottom left)
3. See all available commands
4. Tap any command to use it

**Command menu shows:**
```
/start - 🏠 Welcome & command list
/status - 📊 Quick P&L status
/pnl - 💰 Detailed P&L
/positions - 📍 View positions
... (all 21 commands)
```

---

## Verify Setup

### Checklist

- [ ] Bot created with @BotFather
- [ ] Bot token added to .env
- [ ] Chat ID obtained
- [ ] Chat ID added to .env
- [ ] Commands registered
- [ ] Bot started (python telegram_bot.py)
- [ ] /start command works
- [ ] /status command works
- [ ] Commands appear in menu (/ button)
- [ ] Notifications working

### Test Script

```bash
# Run verification
python verify_telegram.py

# Should show:
# ✅ Bot token configured
# ✅ Chat ID configured
# ✅ Bot responding
# ✅ Commands registered
# ✅ Notifications working
```

---

## Troubleshooting

### Bot Not Responding

**Problem:** Send /start but no response

**Solutions:**
```bash
# 1. Check if bot is running
ps aux | grep telegram_bot.py  # Linux/Mac
tasklist | findstr python      # Windows

# 2. Check bot token
python -c "import config; print(config.TELEGRAM_BOT_TOKEN)"

# 3. Restart bot
python telegram_bot.py

# 4. Check logs
type logs\bot.log  # Windows
cat logs/bot.log   # Linux/Mac
```

---

### Wrong Chat ID

**Problem:** Bot runs but you don't receive messages

**Solutions:**
```bash
# 1. Get chat ID again
python get_chat_id.py

# 2. Verify in .env
python -c "import config; print(config.TELEGRAM_CHAT_ID)"

# 3. Update .env and restart bot
```

---

### Commands Not in Menu

**Problem:** Commands don't appear when tapping /

**Solutions:**
```bash
# 1. Re-register commands
python register_telegram_commands.py

# 2. Manual registration with @BotFather
# Message @BotFather
# Send: /setcommands
# Select your bot
# Paste command list

# 3. Restart Telegram app

# 4. Clear Telegram cache (Settings > Data and Storage > Clear Cache)
```

---

### Import Errors

**Problem:** ModuleNotFoundError when starting bot

**Solutions:**
```bash
# 1. Activate virtual environment
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# 2. Install requirements
pip install -r requirements.txt

# 3. Verify installation
pip list | grep telegram
```

---

## Advanced Configuration

### Custom Welcome Message

Edit `telegram_bot.py`:

```python
def start_command(self, update: Update, context: CallbackContext):
    message = (
        "🤖 **Your Custom Bot Name**\n\n"
        "Your custom welcome message here...\n"
        # ... rest of commands
    )
```

### Add Custom Commands

```python
# 1. Add handler in setup_handlers()
dp.add_handler(CommandHandler("mycommand", self.my_command))

# 2. Create command function
def my_command(self, update: Update, context: CallbackContext):
    update.message.reply_text("My custom response")

# 3. Register with Telegram
# Add to register_telegram_commands.py:
{"command": "mycommand", "description": "My custom command"}
```

### Restrict Access

```python
# Only allow specific users
ALLOWED_USERS = [123456789, 987654321]  # Your chat IDs

def is_authorized(self, update):
    return update.effective_user.id in ALLOWED_USERS

def status_command(self, update, context):
    if not self.is_authorized(update):
        update.message.reply_text("❌ Unauthorized")
        return
    # ... rest of command
```

---

## Multiple Bots

### Setup Multiple Bots

```bash
# Bot 1: Live Trading
TELEGRAM_BOT_TOKEN_LIVE=token1
TELEGRAM_CHAT_ID_LIVE=chatid1

# Bot 2: Paper Trading
TELEGRAM_BOT_TOKEN_PAPER=token2
TELEGRAM_CHAT_ID_PAPER=chatid2
```

### Run Multiple Bots

```bash
# Terminal 1
python telegram_bot.py --mode live

# Terminal 2
python telegram_bot.py --mode paper
```

---

## Security Best Practices

### 1. Keep Token Secret
```bash
# Never commit .env to git
echo ".env" >> .gitignore

# Never share bot token
# Regenerate if compromised (via @BotFather)
```

### 2. Restrict Bot Access
```python
# Add user whitelist
ALLOWED_USERS = [your_chat_id]

# Check on every command
if update.effective_user.id not in ALLOWED_USERS:
    return
```

### 3. Use HTTPS
```python
# Bot API uses HTTPS by default
# Never use HTTP for bot communication
```

### 4. Monitor Bot Activity
```bash
# Check logs regularly
tail -f logs/bot.log

# Monitor unauthorized access attempts
grep "Unauthorized" logs/bot.log
```

---

## Maintenance

### Daily
- Check bot is running: `/bot`
- Verify notifications working

### Weekly
- Review logs: `logs/bot.log`
- Check for errors
- Update if needed

### Monthly
- Backup .env file
- Review command usage
- Update bot features

---

## Quick Reference

### Start Bot
```bash
python telegram_bot.py
```

### Stop Bot
```bash
# Ctrl+C (if running in foreground)
# Or
pkill -f telegram_bot.py  # Linux/Mac
taskkill /F /IM python.exe  # Windows (kills all Python)
```

### Restart Bot
```bash
# Stop and start
pkill -f telegram_bot.py && python telegram_bot.py
```

### Check Status
```bash
# In Telegram
/bot

# Or check process
ps aux | grep telegram_bot.py
```

### View Logs
```bash
tail -f logs/bot.log  # Linux/Mac
type logs\bot.log     # Windows
```

---

## Support

### Documentation
- **TELEGRAM_COMMANDS.md** - All commands
- **telegram_bot.py** - Bot code
- **notifier.py** - Notification functions

### Testing
```bash
python verify_telegram.py  # Test setup
python get_chat_id.py      # Get chat ID
python register_telegram_commands.py  # Register commands
```

### Help
- Check logs: `logs/bot.log`
- Test connection: `/start`
- Verify setup: `python verify_telegram.py`

---

**Your Telegram bot is now fully configured with all 21 commands!** 🎉

Use `/start` in Telegram to see all available commands and start trading! 📱🚀
