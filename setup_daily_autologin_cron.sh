#!/bin/bash
# Setup Daily Auto-Login via Cron
# Runs auto-login at 9:10 AM on weekdays (before market opens at 9:15 AM)

echo "=========================================="
echo "SETUP DAILY AUTO-LOGIN (CRON)"
echo "=========================================="
echo ""

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "This will setup a cron job to run auto-login daily at 9:10 AM (Mon-Fri)"
echo ""
echo "The cron job will:"
echo "  1. Run auto_login.py at 9:10 AM"
echo "  2. Generate fresh access token"
echo "  3. Restart the trading bot service"
echo ""
read -p "Continue? (y/n): " confirm

if [ "$confirm" != "y" ]; then
    echo "Setup cancelled"
    exit 0
fi

# Create cron job
CRON_CMD="10 9 * * 1-5 cd $SCRIPT_DIR && $SCRIPT_DIR/.venv/bin/python $SCRIPT_DIR/auto_login.py >> $SCRIPT_DIR/logs/auto_login_cron.log 2>&1 && sudo systemctl restart kite-trading-bot"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "auto_login.py"; then
    echo ""
    echo "⚠️  Auto-login cron job already exists!"
    echo ""
    echo "Current cron jobs:"
    crontab -l | grep "auto_login"
    echo ""
    read -p "Replace existing cron job? (y/n): " replace
    
    if [ "$replace" != "y" ]; then
        echo "Setup cancelled"
        exit 0
    fi
    
    # Remove old cron job
    crontab -l | grep -v "auto_login.py" | crontab -
fi

# Add new cron job
(crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -

echo ""
echo "✅ Cron job created!"
echo ""
echo "Schedule: 9:10 AM, Monday to Friday"
echo ""
echo "The bot will:"
echo "  1. Auto-login at 9:10 AM"
echo "  2. Auto-restart with fresh token"
echo "  3. Be ready before market opens at 9:15 AM"
echo ""
echo "View cron jobs:"
echo "  crontab -l"
echo ""
echo "View auto-login logs:"
echo "  tail -f $SCRIPT_DIR/logs/auto_login_cron.log"
echo ""
echo "Test auto-login now:"
echo "  python auto_login.py"
echo ""
echo "=========================================="
