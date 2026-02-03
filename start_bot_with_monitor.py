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

# Global kill switch reference
kill_switch = None

def main():
    """Start bot with monitoring enabled"""
    global kill_switch
    
    try:
        logger.info("=" * 60)
        logger.info("STARTING TRADING BOT WITH MONITORING")
        logger.info("=" * 60)
        
        # Initialize kill switch
        logger.info("Initializing Advanced Kill Switch...")
        kill_switch = AdvancedKillSwitch()
        
        # Start monitoring automatically
        logger.info("Starting P&L monitoring...")
        kill_switch.start_monitoring()
        
        logger.info("? Monitoring started successfully!")
        logger.info("Kill switch will trigger on:")
        logger.info(f"  - Loss > {kill_switch.loss_display}")
        logger.info(f"  - Profit drawdown: Peak {kill_switch.profit_display} ? Drop {kill_switch.drawdown_display}")
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
