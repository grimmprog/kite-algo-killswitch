#!/usr/bin/env python3
"""
Start Trading Bot with Monitoring Enabled
Automatically starts the Telegram bot and enables kill switch monitoring
"""
import sys
import time
import logging
from telegram_bot import TradingBot
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

def main():
    """Start bot with monitoring enabled"""
    try:
        logger.info("=" * 60)
        logger.info("STARTING TRADING BOT WITH MONITORING")
        logger.info("=" * 60)
        
        # Initialize the bot
        logger.info("Initializing Telegram bot...")
        bot = TradingBot()
        
        # Initialize kill switch
        logger.info("Initializing Advanced Kill Switch...")
        kill_switch = AdvancedKillSwitch()
        
        # Store kill switch reference in bot
        bot.kill_switch = kill_switch
        
        # Start monitoring automatically
        logger.info("Starting P&L monitoring...")
        kill_switch.start_monitoring()
        
        logger.info("✅ Monitoring started successfully!")
        logger.info("Kill switch will trigger on:")
        logger.info(f"  - Loss > ₹{kill_switch.loss_threshold:,.0f}")
        logger.info(f"  - Profit drawdown: Peak ₹{kill_switch.profit_threshold:,.0f} → Drop ₹{kill_switch.drawdown_threshold:,.0f}")
        logger.info("")
        logger.info("Bot is now running with active monitoring...")
        logger.info("Press Ctrl+C to stop")
        logger.info("=" * 60)
        
        # Start the bot (this will block)
        bot.run()
        
    except KeyboardInterrupt:
        logger.info("\n\nShutting down gracefully...")
        if 'kill_switch' in locals() and kill_switch.is_monitoring():
            logger.info("Stopping monitoring...")
            kill_switch.stop_monitoring()
        logger.info("Bot stopped.")
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
