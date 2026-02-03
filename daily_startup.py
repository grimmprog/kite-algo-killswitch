"""
Daily Startup Script
Runs at 9:15 AM on weekdays to:
1. Generate access token automatically
2. Restart bot services
3. Send startup notification
"""
import schedule
import time
import subprocess
import logging
import os
import platform
from datetime import datetime
from auto_login import AutoLogin

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/daily_startup.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DailyStartup:
    def __init__(self):
        self.os_type = platform.system()
        
    def is_weekday(self):
        """Check if today is a weekday"""
        return datetime.now().weekday() < 5  # Monday = 0, Friday = 4
    
    def generate_token(self):
        """Generate access token automatically"""
        logger.info("=" * 60)
        logger.info("DAILY TOKEN GENERATION")
        logger.info("=" * 60)
        
        if not self.is_weekday():
            logger.info("Today is weekend. Skipping token generation.")
            return False
        
        try:
            auto_login = AutoLogin(headless=True)
            success = auto_login.run()
            return success
        except Exception as e:
            logger.error(f"Token generation failed: {e}")
            return False
    
    def restart_services(self):
        """Restart bot services"""
        logger.info("Restarting bot services...")
        
        try:
            if self.os_type == 'Linux':
                # Restart systemd services
                services = ['kite-bot', 'kite-killswitch', 'kite-telegram']
                for service in services:
                    try:
                        subprocess.run(
                            ['sudo', 'systemctl', 'restart', service],
                            check=True,
                            capture_output=True
                        )
                        logger.info(f"✅ Restarted {service}")
                    except subprocess.CalledProcessError as e:
                        logger.warning(f"Failed to restart {service}: {e}")
            else:
                # Windows - just log (services need to be restarted manually)
                logger.info("⚠️  Windows detected. Please restart bot manually.")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to restart services: {e}")
            return False
    
    def send_startup_notification(self, success):
        """Send Telegram notification"""
        try:
            from notifier import notifier
            
            if success:
                message = (
                    f"🌅 **DAILY STARTUP COMPLETE**\n\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}\n"
                    f"Date: {datetime.now().strftime('%d-%b-%Y')}\n\n"
                    f"✅ Access token generated\n"
                    f"✅ Services restarted\n"
                    f"✅ Bot is ready to trade\n\n"
                    f"Send /status to check bot status"
                )
            else:
                message = (
                    f"⚠️ **DAILY STARTUP FAILED**\n\n"
                    f"Time: {datetime.now().strftime('%H:%M:%S')}\n"
                    f"Date: {datetime.now().strftime('%d-%b-%Y')}\n\n"
                    f"❌ Token generation failed\n\n"
                    f"Please login manually:\n"
                    f"`python login.py`"
                )
            
            notifier.send_message(message)
            logger.info("Startup notification sent")
            
        except Exception as e:
            logger.warning(f"Failed to send notification: {e}")
    
    def run_daily_startup(self):
        """Execute daily startup routine"""
        logger.info("=" * 60)
        logger.info("STARTING DAILY ROUTINE")
        logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)
        
        # Step 1: Generate token
        token_success = self.generate_token()
        
        if not token_success:
            logger.error("Token generation failed. Aborting startup.")
            self.send_startup_notification(False)
            return
        
        # Step 2: Restart services
        time.sleep(2)
        services_success = self.restart_services()
        
        # Step 3: Send notification
        self.send_startup_notification(token_success and services_success)
        
        logger.info("=" * 60)
        logger.info("DAILY STARTUP COMPLETE")
        logger.info("=" * 60)
    
    def schedule_daily_startup(self):
        """Schedule daily startup at 9:15 AM on weekdays"""
        logger.info("=" * 60)
        logger.info("DAILY STARTUP SCHEDULER")
        logger.info("=" * 60)
        logger.info("Scheduled time: 09:15 AM (Mon-Fri)")
        logger.info("=" * 60)
        
        # Schedule for 9:15 AM
        schedule.every().monday.at("09:15").do(self.run_daily_startup)
        schedule.every().tuesday.at("09:15").do(self.run_daily_startup)
        schedule.every().wednesday.at("09:15").do(self.run_daily_startup)
        schedule.every().thursday.at("09:15").do(self.run_daily_startup)
        schedule.every().friday.at("09:15").do(self.run_daily_startup)
        
        logger.info("Scheduler started. Waiting for scheduled time...")
        logger.info("Press Ctrl+C to stop")
        
        # Keep running
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("\nScheduler stopped by user")

def main():
    """Main function"""
    import sys
    
    startup = DailyStartup()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--now':
        # Run immediately (for testing)
        logger.info("Running startup immediately (test mode)")
        startup.run_daily_startup()
    else:
        # Run on schedule
        startup.schedule_daily_startup()

if __name__ == "__main__":
    main()
