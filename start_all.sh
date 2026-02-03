#!/bin/bash
# Startup script for Linux/Ubuntu
# Starts all bot components

echo "=========================================="
echo "KITE ALGO TRADING BOT - STARTUP"
echo "=========================================="

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "✅ Virtual environment activated"
else
    echo "❌ Virtual environment not found!"
    echo "Run: python3 -m venv venv"
    exit 1
fi

# Check if access token exists
if [ ! -f "access_token.txt" ]; then
    echo "⚠️  Access token not found!"
    echo "Run: python login.py"
    read -p "Press Enter to continue anyway or Ctrl+C to exit..."
fi

# Function to start process in background
start_process() {
    local name=$1
    local script=$2
    local log_file="logs/${name}.log"
    
    # Create logs directory if it doesn't exist
    mkdir -p logs
    
    # Check if already running
    if pgrep -f "$script" > /dev/null; then
        echo "⚠️  $name is already running"
    else
        echo "Starting $name..."
        nohup python "$script" > "$log_file" 2>&1 &
        echo "✅ $name started (PID: $!)"
    fi
}

echo ""
echo "Starting bot components..."
echo ""

# Start Telegram bot
start_process "Telegram Bot" "test_telegram_commands.py"

# Start Kill Switch Monitor
start_process "Kill Switch" "continuous_killswitch_monitor.py"

# Start Main Trading Bot
start_process "Trading Bot" "main.py"

echo ""
echo "=========================================="
echo "✅ All components started!"
echo "=========================================="
echo ""
echo "View logs:"
echo "  tail -f logs/telegram_bot.log"
echo "  tail -f logs/kill_switch.log"
echo "  tail -f logs/trading_bot.log"
echo ""
echo "Stop all:"
echo "  ./stop_all.sh"
echo ""
echo "Check status:"
echo "  ps aux | grep python"
echo "=========================================="
