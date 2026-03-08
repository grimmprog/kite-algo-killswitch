#!/bin/bash
# Fix the service to include auto-login before starting the bot

echo "=========================================="
echo "FIXING KITE SERVICE AUTO-LOGIN"
echo "=========================================="
echo ""

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Stop the service if running
echo "Stopping kite-trading-bot service..."
sudo systemctl stop kite-trading-bot 2>/dev/null

# Copy updated service file
echo "Updating service file..."
sudo cp "$SCRIPT_DIR/kite-trading-bot.service" /etc/systemd/system/kite-trading-bot.service

# Reload systemd
echo "Reloading systemd..."
sudo systemctl daemon-reload

# Enable service
echo "Enabling service..."
sudo systemctl enable kite-trading-bot

# Start service
echo "Starting service..."
sudo systemctl start kite-trading-bot

echo ""
echo "✅ Service updated and restarted!"
echo ""
echo "The service will now:"
echo "  1. Check if access token exists and is fresh"
echo "  2. Run auto_login.py with xvfb if needed"
echo "  3. Start the Telegram bot with monitoring"
echo ""
echo "Auto-login works via xvfb (virtual display)"
echo ""
echo "Check status:"
echo "  sudo systemctl status kite-trading-bot"
echo ""
echo "View logs:"
echo "  sudo journalctl -u kite-trading-bot -f"
echo "  tail -f logs/bot_service.log"
echo ""
echo "Test logout/restart:"
echo "  /logout in Telegram"
echo "  Service will auto-restart and login"
echo ""
echo "=========================================="
