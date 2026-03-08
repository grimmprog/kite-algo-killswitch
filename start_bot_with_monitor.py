#!/usr/bin/env python3
"""
Start Trading Bot with Monitoring Enabled
Automatically starts the Telegram bot and enables kill switch monitoring
"""
import sys
import logging
from advanced_killswitch import AdvancedKillSwitch

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global kill switch reference - shared with telegram bot
kill_switch = None

def get_global_kill_switch():
    """Get the global kill switch instance"""
    global kill_switch
    if kill_switch is None:
        logger.info("Creating global AdvancedKillSwitch instance...")
        kill_switch = AdvancedKillSwitch()
        logger.info(f"Global kill switch instance created: {id(kill_switch)}")
    else:
        logger.debug(f"Returning existing global kill switch instance: {id(kill_switch)}")
    return kill_switch

def main():
    """Start bot with monitoring enabled"""
    global kill_switch
    
    try:
        logger.info("=" * 60)
        logger.info("STARTING TRADING BOT WITH MONITORING")
        logger.info("=" * 60)
        
        # Wait a moment to ensure access token is fully written
        import time
        time.sleep(2)
        
        # Verify access token exists
        import os
        token_path = os.path.join(os.path.dirname(__file__), "access_token.txt")
        if not os.path.exists(token_path):
            logger.error("❌ Access token not found! Auto-login may have failed.")
            logger.error("Please check auto-login logs.")
            sys.exit(1)
        
        with open(token_path, 'r') as f:
            token = f.read().strip()
            if not token:
                logger.error("❌ Access token is empty!")
                sys.exit(1)
        
        logger.info(f"✅ Access token found: {token[:10]}...")
        
        # Initialize kill switch
        logger.info("Initializing Advanced Kill Switch...")
        kill_switch = get_global_kill_switch()
        logger.info(f"Global kill switch initialized with ID: {id(kill_switch)}")
        
        # Start monitoring automatically
        logger.info("Starting P&L monitoring...")
        kill_switch.start_monitoring()
        
        logger.info("✅ Monitoring started successfully!")
        logger.info("Kill switch will trigger on:")
        logger.info(f"  - Loss > {kill_switch.loss_display}")
        logger.info(f"  - Profit threshold: {kill_switch.profit_display}")
        logger.info(f"  - Drawdown: {kill_switch.drawdown_display}")
        logger.info("")
        logger.info("Starting Telegram bot...")
        logger.info("Bot is now running with active monitoring...")
        logger.info("Press Ctrl+C to stop")
        logger.info("=" * 60)
        
        # Run telegram_bot.py as a module
        # This will execute the if __name__ == "__main__" block
        import runpy
        runpy.run_module('telegram_bot', run_name='__main__')
        
    except KeyboardInterrupt:
        logger.info("\n\nShutting down gracefully...")
        if kill_switch and kill_switch.is_monitoring():
            logger.info("Stopping monitoring...")
            kill_switch.stop_monitoring()
        logger.info("Bot stopped.")
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        if kill_switch and kill_switch.is_monitoring():
            kill_switch.stop_monitoring()
        sys.exit(1)

if __name__ == "__main__":
    main()
