#!/bin/bash
# AWS Ubuntu Deployment Script for Kite Trading Bot
# This script sets up everything needed to run the bot with monitoring on AWS

set -e  # Exit on error

echo "============================================================"
echo "KITE TRADING BOT - AWS UBUNTU DEPLOYMENT"
echo "============================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$SCRIPT_DIR"

echo -e "${GREEN}Project directory: $PROJECT_DIR${NC}"
echo ""

# Step 1: Update system
echo "Step 1: Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Step 2: Install Python 3.10+
echo ""
echo "Step 2: Installing Python 3.10+..."
sudo apt-get install -y python3 python3-pip python3-venv

# Check Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Python version: $PYTHON_VERSION"

# Step 3: Install Chrome and ChromeDriver
echo ""
echo "Step 3: Installing Chrome and ChromeDriver..."

# Install dependencies
sudo apt-get install -y wget curl unzip xvfb libxi6 libgconf-2-4

# Install Chrome
if ! command -v google-chrome &> /dev/null; then
    echo "Installing Google Chrome..."
    wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
    sudo apt-get update
    sudo apt-get install -y google-chrome-stable
    echo "✅ Chrome installed"
else
    echo "✅ Chrome already installed"
fi

# Verify Chrome installation
google-chrome --version

# Step 4: Create virtual environment
echo ""
echo "Step 4: Setting up Python virtual environment..."
cd "$PROJECT_DIR"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
source .venv/bin/activate

# Step 5: Install Python dependencies
echo ""
echo "Step 5: Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ Dependencies installed"

# Step 6: Create logs directory
echo ""
echo "Step 6: Creating logs directory..."
mkdir -p logs
echo "✅ Logs directory created"

# Step 7: Configure environment variables
echo ""
echo "Step 7: Checking environment configuration..."
if [ ! -f ".env" ]; then
    echo -e "${RED}ERROR: .env file not found!${NC}"
    echo "Please create .env file with your credentials:"
    echo "  - KITE_USER_ID"
    echo "  - KITE_PASSWORD"
    echo "  - KITE_TOTP_KEY"
    echo "  - TELEGRAM_BOT_TOKEN"
    echo "  - TELEGRAM_CHAT_ID"
    exit 1
else
    echo "✅ .env file found"
fi

# Step 8: Set up systemd service
echo ""
echo "Step 8: Setting up systemd service..."

# Update service file with correct paths
SERVICE_FILE="kite-trading-bot.service"
TEMP_SERVICE="/tmp/kite-trading-bot.service"

# Replace placeholder paths with actual paths
sed "s|/home/ubuntu/kite-algo|$PROJECT_DIR|g" "$SERVICE_FILE" > "$TEMP_SERVICE"

# Copy service file to systemd
sudo cp "$TEMP_SERVICE" /etc/systemd/system/kite-trading-bot.service
sudo systemctl daemon-reload

echo "✅ Systemd service configured"

# Step 9: Set up auto-login cron job
echo ""
echo "Step 9: Setting up auto-login cron job..."

# Create cron job for auto-login at 8:45 AM weekdays
CRON_JOB="45 8 * * 1-5 cd $PROJECT_DIR && $PROJECT_DIR/.venv/bin/python $PROJECT_DIR/auto_login.py >> $PROJECT_DIR/logs/auto_login.log 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "auto_login.py"; then
    echo "✅ Auto-login cron job already exists"
else
    # Add cron job
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "✅ Auto-login cron job added (8:45 AM weekdays)"
fi

# Step 10: Make scripts executable
echo ""
echo "Step 10: Making scripts executable..."
chmod +x start_bot_with_monitor.py
chmod +x auto_login.py
chmod +x aws_deploy.sh
echo "✅ Scripts are executable"

# Step 11: Test configuration
echo ""
echo "Step 11: Testing configuration..."

# Test Python imports
echo "Testing Python imports..."
python3 -c "import selenium; import pyotp; import telebot; print('✅ All imports successful')"

# Test Chrome
echo "Testing Chrome..."
google-chrome --version > /dev/null && echo "✅ Chrome working"

echo ""
echo "============================================================"
echo "DEPLOYMENT COMPLETE!"
echo "============================================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Start the bot service:"
echo "   sudo systemctl start kite-trading-bot"
echo ""
echo "2. Enable auto-start on boot:"
echo "   sudo systemctl enable kite-trading-bot"
echo ""
echo "3. Check service status:"
echo "   sudo systemctl status kite-trading-bot"
echo ""
echo "4. View logs:"
echo "   tail -f logs/bot_monitor.log"
echo ""
echo "5. Stop the service:"
echo "   sudo systemctl stop kite-trading-bot"
echo ""
echo "The bot will:"
echo "  - Auto-login at 8:45 AM on weekdays"
echo "  - Run continuously with monitoring enabled"
echo "  - Auto-deactivate segments when kill switch triggers"
echo "  - Restart automatically if it crashes"
echo ""
echo "============================================================"
