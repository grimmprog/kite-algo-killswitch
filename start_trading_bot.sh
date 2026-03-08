#!/bin/bash
# Wrapper script to run auto-login first, then start the bot
# Uses xvfb for virtual display to run Chrome in headless mode

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "KITE TRADING BOT STARTUP"
echo "=========================================="
echo "$(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Check if access token exists and is recent
TOKEN_FILE="$SCRIPT_DIR/access_token.txt"
NEED_LOGIN=false

if [ ! -f "$TOKEN_FILE" ]; then
    echo "⚠️  Access token not found"
    NEED_LOGIN=true
else
    # Check token age (tokens are valid for 24 hours)
    TOKEN_AGE=$(($(date +%s) - $(stat -c %Y "$TOKEN_FILE" 2>/dev/null || stat -f %m "$TOKEN_FILE" 2>/dev/null)))
    TOKEN_AGE_HOURS=$((TOKEN_AGE / 3600))
    
    if [ $TOKEN_AGE -lt 86400 ]; then
        echo "✅ Valid access token found (age: ${TOKEN_AGE_HOURS}h)"
        NEED_LOGIN=false
    else
        echo "⚠️  Access token is old (age: ${TOKEN_AGE_HOURS}h)"
        NEED_LOGIN=true
    fi
fi

# Run auto-login if needed
if [ "$NEED_LOGIN" = true ]; then
    echo ""
    echo "Step 1: Running auto-login with virtual display..."
    
    # Use xvfb-run to provide virtual display for Chrome
    xvfb-run -a --server-args="-screen 0 1920x1080x24" \
        "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/auto_login.py"
    
    if [ $? -eq 0 ]; then
        echo "✅ Auto-login successful!"
        echo ""
    else
        echo "❌ Auto-login failed!"
        echo ""
        echo "Troubleshooting:"
        echo "  1. Check logs: tail -f logs/bot_service_error.log"
        echo "  2. Verify TOTP key in .env"
        echo "  3. Test manually: python auto_login.py"
        echo ""
        exit 1
    fi
fi

# Start bot with monitoring
echo "Step 2: Starting bot with monitoring..."
echo ""
exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/start_bot_with_monitor.py"
