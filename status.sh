#!/bin/bash
# Check status of all bot processes

echo "=========================================="
echo "BOT STATUS CHECK"
echo "=========================================="
echo ""

# Function to check process status
check_status() {
    local name=$1
    local script=$2
    
    if pgrep -f "$script" > /dev/null; then
        pid=$(pgrep -f "$script")
        echo "✅ $name: RUNNING (PID: $pid)"
    else
        echo "❌ $name: STOPPED"
    fi
}

# Check all components
check_status "Telegram Bot" "test_telegram_commands.py"
check_status "Kill Switch Monitor" "advanced_killswitch.py"
check_status "Trading Bot" "main.py"

echo ""
echo "=========================================="
echo "SYSTEM RESOURCES"
echo "=========================================="

# Memory usage
echo ""
echo "Memory Usage:"
free -h | grep -E "Mem|Swap"

# Disk usage
echo ""
echo "Disk Usage:"
df -h | grep -E "Filesystem|/$"

# CPU load
echo ""
echo "CPU Load:"
uptime

echo ""
echo "=========================================="
echo "RECENT LOGS (last 5 lines each)"
echo "=========================================="

for log in logs/*.log; do
    if [ -f "$log" ]; then
        echo ""
        echo "📄 $(basename $log):"
        tail -n 5 "$log" 2>/dev/null || echo "  (empty or not found)"
    fi
done

echo ""
echo "=========================================="
