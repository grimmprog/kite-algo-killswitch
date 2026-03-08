#!/bin/bash
# Setup Split Cron Jobs for Auto-Login
# Separates auto-login and service restart into two jobs for better reliability

echo "=========================================="
echo "SETUP SPLIT CRON JOBS"
echo "=========================================="
echo ""

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "This will setup TWO cron jobs:"
echo ""
echo "1. User cron (ubuntu): Auto-login at 9:10 AM"
echo "2. Root cron: Service restart at 9:11 AM"
echo ""
echo "This approach is more reliable because:"
echo "  • Auto-login runs in user context (has display access)"
echo "  • Service restart runs as root (no sudo permission issues)"
echo "  • Jobs are independent (one failure doesn't affect the other)"
echo ""
read -p "Continue? (y/n): " confirm

if [ "$confirm" != "y" ]; then
    echo "Setup cancelled"
    exit 0
fi

echo ""
echo "Step 1: Setting up user cron job (auto-login)..."
echo "================================================"

# User cron job - just auto-login
USER_CRON_CMD="10 9 * * 1-5 cd $SCRIPT_DIR && $SCRIPT_DIR/.venv/bin/python $SCRIPT_DIR/auto_login.py >> $SCRIPT_DIR/logs/auto_login_cron.log 2>&1"

# Remove old cron job if exists
if crontab -l 2>/dev/null | grep -q "auto_login.py"; then
    echo "Removing old cron job..."
    crontab -l | grep -v "auto_login.py" | crontab -
fi

# Add new user cron job
(crontab -l 2>/dev/null; echo "$USER_CRON_CMD") | crontab -

echo "✅ User cron job created!"
echo ""
echo "Current user cron jobs:"
crontab -l | grep "auto_login"
echo ""

echo "Step 2: Setting up root cron job (service restart)..."
echo "======================================================"

# Root cron job - just service restart
ROOT_CRON_CMD="11 9 * * 1-5 systemctl restart kite-trading-bot"

# Check if root cron job already exists
if sudo crontab -l 2>/dev/null | grep -q "kite-trading-bot"; then
    echo "⚠️  Root cron job already exists!"
    echo ""
    echo "Current root cron jobs:"
    sudo crontab -l | grep "kite-trading-bot"
    echo ""
    read -p "Replace existing root cron job? (y/n): " replace
    
    if [ "$replace" != "y" ]; then
        echo "Skipping root cron job setup"
    else
        # Remove old root cron job
        sudo crontab -l | grep -v "kite-trading-bot" | sudo crontab -
        # Add new root cron job
        (sudo crontab -l 2>/dev/null; echo "$ROOT_CRON_CMD") | sudo crontab -
        echo "✅ Root cron job updated!"
    fi
else
    # Add new root cron job
    (sudo crontab -l 2>/dev/null; echo "$ROOT_CRON_CMD") | sudo crontab -
    echo "✅ Root cron job created!"
fi

echo ""
echo "=========================================="
echo "✅ SETUP COMPLETE!"
echo "=========================================="
echo ""
echo "Schedule:"
echo "  9:10 AM - Auto-login (generates token)"
echo "  9:11 AM - Service restart (uses new token)"
echo "  9:15 AM - Market opens (bot is ready!)"
echo ""
echo "View user cron jobs:"
echo "  crontab -l"
echo ""
echo "View root cron jobs:"
echo "  sudo crontab -l"
echo ""
echo "View auto-login logs:"
echo "  tail -f $SCRIPT_DIR/logs/auto_login_cron.log"
echo ""
echo "View service logs:"
echo "  sudo journalctl -u kite-trading-bot -f"
echo ""
echo "Test auto-login now:"
echo "  .venv/bin/python auto_login.py"
echo ""
echo "Test service restart:"
echo "  sudo systemctl restart kite-trading-bot"
echo ""
echo "=========================================="
