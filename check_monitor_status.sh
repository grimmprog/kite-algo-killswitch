#!/bin/bash
# Quick script to check if monitoring is active

echo "============================================================"
echo "MONITORING STATUS CHECK"
echo "============================================================"
echo ""

# Check if service is running
echo "1. Service Status:"
if systemctl is-active --quiet kite-trading-bot; then
    echo "   ✅ Service is RUNNING"
else
    echo "   ❌ Service is STOPPED"
    echo ""
    echo "Start with: sudo systemctl start kite-trading-bot"
    exit 1
fi

echo ""

# Check logs for monitoring status
echo "2. Monitoring Status:"
if tail -n 50 logs/bot_monitor.log 2>/dev/null | grep -q "Monitoring started"; then
    echo "   ✅ Monitoring is ACTIVE"
else
    echo "   ⚠️  Monitoring status unclear"
fi

echo ""

# Show last few log entries
echo "3. Recent Activity (last 10 lines):"
echo "-----------------------------------------------------------"
tail -n 10 logs/bot_monitor.log 2>/dev/null || echo "   No logs found"
echo "-----------------------------------------------------------"

echo ""

# Check for errors
echo "4. Recent Errors:"
ERROR_COUNT=$(tail -n 100 logs/*.log 2>/dev/null | grep -i error | wc -l)
if [ "$ERROR_COUNT" -eq 0 ]; then
    echo "   ✅ No recent errors"
else
    echo "   ⚠️  Found $ERROR_COUNT error(s) in last 100 lines"
    echo "   View with: tail -n 100 logs/*.log | grep -i error"
fi

echo ""
echo "============================================================"
echo "For real-time monitoring: tail -f logs/bot_monitor.log"
echo "For Telegram status: Send /status to your bot"
echo "============================================================"
