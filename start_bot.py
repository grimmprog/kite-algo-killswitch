"""
Startup script for Kite Algo Trading Bot
Performs pre-flight checks before starting the bot
"""
import os
import sys
from datetime import datetime
from connect import get_kite_session
import config

def check_access_token():
    """Check if access token exists and is valid"""
    print("1. Checking Kite API access token...")
    try:
        kite = get_kite_session()
        profile = kite.profile()
        print(f"   ✅ Connected as: {profile['user_name']} ({profile['user_id']})")
        return True
    except Exception as e:
        print(f"   ❌ Access token invalid or missing: {e}")
        print(f"   → Run: python login.py")
        return False

def check_telegram():
    """Check if Telegram is configured"""
    print("2. Checking Telegram configuration...")
    if not config.TELEGRAM_BOT_TOKEN or config.TELEGRAM_BOT_TOKEN == "your_telegram_bot_token_here":
        print("   ❌ Telegram bot token not configured")
        return False
    if not config.TELEGRAM_CHAT_ID or config.TELEGRAM_CHAT_ID == "your_telegram_chat_id_here":
        print("   ❌ Telegram chat ID not configured")
        return False
    print(f"   ✅ Telegram configured (Chat ID: {config.TELEGRAM_CHAT_ID})")
    return True

def check_trading_hours():
    """Check if within trading hours"""
    print("3. Checking trading hours...")
    now = datetime.now().time()
    if config.START_TIME <= now <= config.AUTO_SQUARE_OFF_TIME:
        print(f"   ✅ Within trading hours ({now.strftime('%H:%M')})")
        return True
    else:
        print(f"   ⚠️  Outside trading hours ({now.strftime('%H:%M')})")
        print(f"   Trading window: {config.START_TIME} - {config.AUTO_SQUARE_OFF_TIME}")
        return False

def check_risk_settings():
    """Display risk settings"""
    print("4. Risk Management Settings:")
    print(f"   Capital: ₹{config.CAPITAL:,}")
    print(f"   Max Daily Loss: ₹{config.MAX_DAILY_LOSS:,}")
    print(f"   Max Trades/Day: {config.MAX_TRADES_PER_DAY}")
    print(f"   Max Active Trades: {config.MAX_ACTIVE_TRADES}")
    print(f"   Confidence Threshold: {config.CONFIDENCE_THRESHOLD}%")
    return True

def main():
    print("=" * 60)
    print("KITE ALGO TRADING BOT - PRE-FLIGHT CHECK")
    print("=" * 60)
    print()
    
    checks = [
        check_access_token(),
        check_telegram(),
        check_trading_hours(),
        check_risk_settings()
    ]
    
    print()
    print("=" * 60)
    
    if not checks[0]:  # Access token is critical
        print("❌ CRITICAL: Cannot start without valid access token")
        sys.exit(1)
    
    if not checks[1]:  # Telegram is important but not critical
        print("⚠️  WARNING: Telegram not configured - no notifications")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(1)
    
    print()
    print("✅ All checks passed!")
    print()
    response = input("Start the trading bot? (y/n): ")
    
    if response.lower() == 'y':
        print()
        print("🚀 Starting bot...")
        print("=" * 60)
        print()
        
        # Import and run main
        from main import main_loop
        main_loop()
    else:
        print("Bot startup cancelled.")

if __name__ == "__main__":
    main()
