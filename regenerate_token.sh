#!/bin/bash
# Regenerate access token to activate new API subscriptions

echo "=========================================="
echo "REGENERATE ACCESS TOKEN"
echo "=========================================="
echo ""
echo "This will:"
echo "1. Run auto-login to get new access token"
echo "2. Restart the trading bot"
echo ""
echo "Your new API subscription will be activated."
echo ""
read -p "Continue? (y/n): " confirm

if [ "$confirm" != "y" ]; then
    echo "Cancelled"
    exit 0
fi

echo ""
echo "Step 1: Running auto-login..."
.venv/bin/python auto_login.py

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ New access token generated"
    echo ""
    echo "Step 2: Restarting bot..."
    sudo systemctl restart kite-trading-bot
    sleep 3
    sudo systemctl status kite-trading-bot --no-pager | head -10
    echo ""
    echo "✅ Bot restarted with new token"
    echo ""
    echo "Test the new subscription:"
    echo "  python test_quote_api.py"
else
    echo ""
    echo "❌ Auto-login failed"
    echo "Try manual login: python login.py"
fi
