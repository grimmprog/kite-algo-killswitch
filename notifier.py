"""
Telegram Notifier - Lightweight wrapper
Uses the full-featured telegram_bot.py for all bot functionality
This module provides a simple interface for sending notifications
"""
import logging
import telegram
import config

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self):
        self.bot_token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.bot = None
        
        if self.bot_token and self.bot_token != "your_telegram_bot_token_here":
            try:
                self.bot = telegram.Bot(token=self.bot_token)
                logger.info("Telegram notifier initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Telegram bot: {e}")
                self.bot = None
    
    def send_message(self, message):
        """Send a simple text message"""
        if self.bot and self.chat_id:
            try:
                self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode='Markdown')
                logger.info("Telegram message sent")
            except Exception as e:
                logger.error(f"Failed to send telegram message: {e}")
        else:
            logger.warning("Telegram not configured - message not sent")
    
    def request_confirmation(self, trade_details):
        """
        Legacy method for trade confirmation
        Returns False (auto-reject) since interactive bot should be run separately
        """
        logger.warning("Trade confirmation requested but interactive bot not running")
        logger.warning("Run 'python telegram_bot.py' separately for interactive features")
        
        # Send notification about the trade
        message = (
            f"🚨 **TRADE SIGNAL** (Auto-rejected)\n\n"
            f"Symbol: {trade_details.get('symbol', 'N/A')}\n"
            f"Type: {trade_details.get('transaction_type', 'N/A')}\n"
            f"Confidence: {trade_details.get('confidence', 'N/A')}\n\n"
            f"⚠️ Run `python telegram_bot.py` for interactive approval"
        )
        self.send_message(message)
        return False
    
    def stop(self):
        """Cleanup method (no-op for simple notifier)"""
        pass

# Global instance
notifier = TelegramNotifier()

# Note: For full bot features (status, positions, kill switch, segments, monitoring),
# run telegram_bot.py separately:
#   python telegram_bot.py
#
# This notifier is only for sending simple messages from the trading system.
