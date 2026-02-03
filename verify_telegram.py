import logging
import config
import time
from notifier import notifier

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_telegram():
    print("Testing Telegram Bot Connection...")
    print(f"Token: {config.TELEGRAM_BOT_TOKEN}")
    print(f"Chat ID: {config.TELEGRAM_CHAT_ID}")
    
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("❌ Telegram credentials missing in config.py / .env")
        return

    # 1. Send simple message
    notifier.send_message("🔔 Test Notification from Kite Algo Bot.")
    print("✅ Notification sent. Check your Telegram.")
    
    # 2. Test Buttons
    print("\nSending Interactive Confirmation Test...")
    dummy_trade = {
        "symbol": "NSE:TEST",
        "transaction_type": "BUY",
        "strike_price": 18000,
        "price": 100.5,
        "stop_loss": 90,
        "confidence": 85
    }
    
    approved = notifier.request_confirmation(dummy_trade)
    
    if approved:
        print("✅ You clicked APPROVE.")
    else:
        print("❌ You clicked REJECT or Timed Out.")

    print("\nTelegram Verification Complete.")
    notifier.stop()

if __name__ == "__main__":
    test_telegram()
