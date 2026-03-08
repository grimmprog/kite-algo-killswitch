"""
Test Telegram Commands
Starts the notifier with all commands enabled
"""
from notifier import notifier
import time

print("=" * 60)
print("TELEGRAM BOT WITH ALL COMMANDS")
print("=" * 60)
print("\nAvailable Commands:")
print("  /start or /help - Show all commands")
print("  /status - Quick P&L status")
print("  /pnl - Detailed P&L")
print("  /positions - View positions")
print("  /orders - Today's orders")
print("  /capital - Capital info")
print("  /killswitch - Kill switch status")
print("  /monitor - Monitoring info")
print("  /close - Close all positions")
print("=" * 60)
print("\nBot is running. Send commands to your Telegram bot.")
print("Press Ctrl+C to stop.\n")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n\nStopping bot...")
    notifier.stop()
    print("Bot stopped.")
