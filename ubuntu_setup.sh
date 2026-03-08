#!/bin/bash

# Ubuntu Server Setup Script for Kite Algo Trading Bot
# Run this script on a fresh Ubuntu server to set up everything

set -e  # Exit on error

echo "=========================================="
echo "Kite Algo Trading Bot - Ubuntu Setup"
echo "=========================================="
echo ""

# Get username
CURRENT_USER=$(whoami)
PROJECT_DIR="$HOME/trading"

echo "Current user: $CURRENT_USER"
echo "Project directory: $PROJECT_DIR"
echo ""

# Check if running as root
if [ "$CURRENT_USER" = "root" ]; then
    echo "❌ Please run this script as a regular user, not root"
    exit 1
fi

# Update system
echo "1. Updating system..."
sudo apt update
sudo apt upgrade -y

# Install dependencies
echo ""
echo "2. Installing dependencies..."
sudo apt install -y python3 python3-pip python3-venv
sudo apt install -y chromium-browser chromium-chromedriver
sudo apt install -y wget unzip xvfb
sudo apt install -y libglib2.0-0 libnss3 libgconf-2-4 libfontconfig1

# Create project directory if it doesn't exist
if [ ! -d "$PROJECT_DIR" ]; then
    echo ""
    echo "3. Creating project directory..."
    mkdir -p "$PROJECT_DIR"
    echo "✅ Created $PROJECT_DIR"
    echo ""
    echo "⚠️  Please upload your project files to: $PROJECT_DIR"
    echo "Then run this script again."
    exit 0
fi

cd "$PROJECT_DIR"

# Create virtual environment
echo ""
echo "4. Creating virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
source .venv/bin/activate

# Install Python packages
echo ""
echo "5. Installing Python packages..."
if [ -f "requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "✅ Python packages installed"
else
    echo "❌ requirements.txt not found"
    exit 1
fi

# Create logs directory
echo ""
echo "6. Creating logs directory..."
mkdir -p logs
echo "✅ Logs directory created"

# Create daily login script
echo ""
echo "7. Creating daily login script..."
cat > daily_login.sh << 'EOF'
#!/bin/bash

# Daily Auto-Login Script
cd $(dirname "$0")
source .venv/bin/activate
python auto_login.py >> logs/autologin_$(date +%Y%m%d).log 2>&1
deactivate
EOF

chmod +x daily_login.sh
echo "✅ daily_login.sh created"

# Create bot startup script
echo ""
echo "8. Creating bot startup script..."
cat > start_telegram_bot.sh << 'EOF'
#!/bin/bash

# Telegram Bot Startup Script
cd $(dirname "$0")
source .venv/bin/activate

# Kill any existing bot instances
pkill -f "python.*telegram_bot.py" 2>/dev/null

# Start bot
nohup python telegram_bot.py >> logs/telegram_bot_$(date +%Y%m%d).log 2>&1 &

echo "Telegram bot started. PID: $!"
EOF

chmod +x start_telegram_bot.sh
echo "✅ start_telegram_bot.sh created"

# Create backup script
echo ""
echo "9. Creating backup script..."
cat > backup.sh << 'EOF'
#!/bin/bash

BACKUP_DIR=~/trading_backups
mkdir -p $BACKUP_DIR
DATE=$(date +%Y%m%d)

# Backup important files
tar -czf $BACKUP_DIR/trading_backup_$DATE.tar.gz \
    .env \
    access_token.txt \
    killswitch_status.json \
    logs 2>/dev/null

# Keep only last 7 backups
ls -t $BACKUP_DIR/trading_backup_*.tar.gz 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null

echo "Backup created: trading_backup_$DATE.tar.gz"
EOF

chmod +x backup.sh
echo "✅ backup.sh created"

# Create log rotation script
echo ""
echo "10. Creating log rotation script..."
cat > rotate_logs.sh << 'EOF'
#!/bin/bash

cd logs
gzip *_$(date -d "yesterday" +%Y%m%d).log 2>/dev/null
find . -name "*.log.gz" -mtime +7 -delete 2>/dev/null
EOF

chmod +x rotate_logs.sh
echo "✅ rotate_logs.sh created"

# Check .env file
echo ""
echo "11. Checking configuration..."
if [ ! -f ".env" ]; then
    echo "❌ .env file not found"
    echo "Please create .env file with your configuration"
    exit 1
else
    echo "✅ .env file found"
    chmod 600 .env
fi

# Test TOTP
echo ""
echo "12. Testing TOTP..."
if python test_totp.py; then
    echo "✅ TOTP test passed"
else
    echo "⚠️  TOTP test failed - please check your TOTP_KEY in .env"
fi

# Setup cron jobs
echo ""
echo "13. Setting up cron jobs..."
echo ""
echo "Add these lines to your crontab (crontab -e):"
echo ""
echo "# Auto-login every weekday at 8:45 AM"
echo "45 8 * * 1-5 $PROJECT_DIR/daily_login.sh"
echo ""
echo "# Start Telegram bot every weekday at 8:50 AM"
echo "50 8 * * 1-5 $PROJECT_DIR/start_telegram_bot.sh"
echo ""
echo "# Backup daily at 4:00 PM"
echo "0 16 * * 1-5 $PROJECT_DIR/backup.sh"
echo ""
echo "# Rotate logs daily at midnight"
echo "0 0 * * * $PROJECT_DIR/rotate_logs.sh"
echo ""

read -p "Do you want to add these cron jobs now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Backup existing crontab
    crontab -l > /tmp/crontab_backup_$(date +%Y%m%d) 2>/dev/null || true
    
    # Add new cron jobs
    (crontab -l 2>/dev/null; echo ""; echo "# Kite Algo Trading Bot"; \
     echo "45 8 * * 1-5 $PROJECT_DIR/daily_login.sh"; \
     echo "50 8 * * 1-5 $PROJECT_DIR/start_telegram_bot.sh"; \
     echo "0 16 * * 1-5 $PROJECT_DIR/backup.sh"; \
     echo "0 0 * * * $PROJECT_DIR/rotate_logs.sh") | crontab -
    
    echo "✅ Cron jobs added"
else
    echo "⚠️  Skipped cron job setup - add them manually later"
fi

# Final summary
echo ""
echo "=========================================="
echo "Setup Complete! 🎉"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Test auto-login:"
echo "   ./daily_login.sh"
echo ""
echo "2. Start Telegram bot:"
echo "   ./start_telegram_bot.sh"
echo ""
echo "3. Test in Telegram:"
echo "   Send /start to your bot"
echo ""
echo "4. Check logs:"
echo "   tail -f logs/telegram_bot_$(date +%Y%m%d).log"
echo ""
echo "5. View cron jobs:"
echo "   crontab -l"
echo ""
echo "For detailed documentation, see:"
echo "   UBUNTU_DEPLOYMENT_GUIDE.md"
echo ""
echo "=========================================="
