#!/bin/bash
# Script to restart the Telegram bot with monitoring

echo "Stopping any running bot processes..."
pkill -f "python.*telegram_bot" || true
pkill -f "python.*start_bot_with_monitor" || true

sleep 2

echo "Starting bot with monitoring..."
source .venv/bin/activate
nohup python3 start_bot_with_monitor.py > bot.log 2>&1 &

echo "Bot started. Check bot.log for output."
echo "You can also check with: tail -f bot.log"