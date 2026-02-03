#!/bin/bash
# Setup Daily Auto-Login
# Creates systemd service or cron job for automatic token generation

echo "=========================================="
echo "DAILY AUTO-LOGIN SETUP"
echo "=========================================="
echo ""
echo "This will setup automatic token generation at 9:15 AM (Mon-Fri)"
echo ""
echo "Choose method:"
echo "1. Systemd Service (Recommended for Ubuntu/AWS)"
echo "2. Cron Job (Alternative)"
echo "3. Test auto-login now"
echo ""
read -p "Select option (1/2/3): " choice

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [ "$choice" == "1" ]; then
    echo ""
    echo "Creating systemd service..."
    
    # Create service file
    sudo tee /etc/systemd/system/kite-daily-startup.service > /dev/null <<EOF
[Unit]
Description=Kite Daily Startup (Auto-Login at 9:15 AM)
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
Environment="PATH=$SCRIPT_DIR/venv/bin"
ExecStart=$SCRIPT_DIR/venv/bin/python $SCRIPT_DIR/daily_startup.py
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd
    sudo systemctl daemon-reload
    
    # Enable service
    sudo systemctl enable kite-daily-startup
    
    # Start service
    sudo systemctl start kite-daily-startup
    
    echo ""
    echo "✅ Systemd service created and started!"
    echo ""
    echo "Service will run daily at 9:15 AM (Mon-Fri)"
    echo ""
    echo "Useful commands:"
    echo "  sudo systemctl status kite-daily-startup"
    echo "  sudo systemctl restart kite-daily-startup"
    echo "  sudo journalctl -u kite-daily-startup -f"
    echo ""

elif [ "$choice" == "2" ]; then
    echo ""
    echo "Setting up cron job..."
    
    # Create cron job
    CRON_CMD="15 9 * * 1-5 cd $SCRIPT_DIR && $SCRIPT_DIR/venv/bin/python $SCRIPT_DIR/auto_login.py >> $SCRIPT_DIR/logs/auto_login.log 2>&1"
    
    # Add to crontab
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    
    echo ""
    echo "✅ Cron job created!"
    echo ""
    echo "Schedule: 9:15 AM, Monday to Friday"
    echo ""
    echo "View cron jobs:"
    echo "  crontab -l"
    echo ""
    echo "View logs:"
    echo "  tail -f $SCRIPT_DIR/logs/auto_login.log"
    echo ""

elif [ "$choice" == "3" ]; then
    echo ""
    echo "Testing auto-login now..."
    echo ""
    
    cd "$SCRIPT_DIR"
    source venv/bin/activate
    python auto_login.py
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ Auto-login test successful!"
        echo ""
        echo "Access token saved to: access_token.txt"
        echo ""
    else
        echo ""
        echo "❌ Auto-login test failed!"
        echo ""
        echo "Check:"
        echo "  1. TOTP key configured in .env"
        echo "  2. Chrome/Chromium installed"
        echo "  3. Credentials correct"
        echo ""
    fi

else
    echo "Invalid option"
    exit 1
fi

echo "=========================================="
