#!/bin/bash
# Test Auto-Login Service Flow
# This script helps you verify that the service properly runs auto-login

echo "=========================================="
echo "AUTO-LOGIN SERVICE TEST"
echo "=========================================="
echo ""

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "This test will:"
echo "  1. Logout (delete access token)"
echo "  2. Restart the service"
echo "  3. Monitor logs to verify auto-login runs"
echo ""
read -p "Continue? (y/n): " confirm

if [ "$confirm" != "y" ]; then
    echo "Test cancelled"
    exit 0
fi

echo ""
echo "Step 1: Logging out..."
echo "----------------------------------------"
python logout.py

if [ ! -f "access_token.txt" ]; then
    echo "✅ Access token removed"
else
    echo "⚠️  Access token still exists"
fi

echo ""
echo "Step 2: Restarting service..."
echo "----------------------------------------"
sudo systemctl restart kite-trading-bot

echo "✅ Service restarted"
echo ""

echo "Step 3: Monitoring logs (Ctrl+C to stop)..."
echo "----------------------------------------"
echo "Watch for:"
echo "  • 'Running auto-login...'"
echo "  • 'Auto-login successful'"
echo "  • 'Starting bot with monitoring...'"
echo ""
sleep 2

# Follow logs
sudo journalctl -u kite-trading-bot -f -n 50
