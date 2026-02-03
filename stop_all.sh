#!/bin/bash
# Stop all bot processes

echo "=========================================="
echo "STOPPING ALL BOT PROCESSES"
echo "=========================================="

# Function to stop process
stop_process() {
    local name=$1
    local script=$2
    
    pids=$(pgrep -f "$script")
    
    if [ -z "$pids" ]; then
        echo "ℹ️  $name is not running"
    else
        echo "Stopping $name (PIDs: $pids)..."
        pkill -f "$script"
        sleep 1
        
        # Force kill if still running
        if pgrep -f "$script" > /dev/null; then
            echo "  Force killing..."
            pkill -9 -f "$script"
        fi
        
        echo "✅ $name stopped"
    fi
}

# Stop all components
stop_process "Telegram Bot" "test_telegram_commands.py"
stop_process "Kill Switch" "advanced_killswitch.py"
stop_process "Trading Bot" "main.py"

echo ""
echo "=========================================="
echo "✅ All processes stopped"
echo "=========================================="
