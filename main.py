import time
import logging
import datetime
from scanner import market_scanner
from notifier import notifier
from execution import execution_manager
import config
from exit_manager import exit_manager

# Setup logging
# Create logs directory if it doesn't exist
import os
if not os.path.exists(config.LOG_DIR):
    os.makedirs(config.LOG_DIR)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(config.LOG_DIR + "/bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main_loop():
    logger.info("Bot Started. Waiting for market hours...")
    
    # Simple loop
    while True:
        try:
            now = datetime.datetime.now()
            
            # Check End Time
            if now.time() > config.END_TIME:
                logger.info("Market Closed for Entries.")
                # Could continue for Exit Manage
                # break?
                pass
                
            # Run Scanner
            signals = market_scanner.scan()
            
            for signal in signals:
                # 1. Notifier Confirmation
                logger.info(f"Asking for confirmation on {signal['symbol']}")
                
                approved = notifier.request_confirmation(signal)
                
                if approved:
                    logger.info("User Approved. Executing...")
                    order_id = execution_manager.place_order(signal)
                    if order_id:
                        notifier.send_message(f"✅ Order Placed: {order_id}")
                    else:
                        notifier.send_message("❌ Order Failed.")
                else:
                    logger.info("User Rejected or Timed out.")
                    
            # Sleep (rate limit / interval)
            # Scan every 1 minute?
            time.sleep(60)
            
        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
            notifier.stop()
            break
        except Exception as e:
            logger.error(f"Main Loop Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main_loop()
