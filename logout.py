#!/usr/bin/env python3
"""
Logout Script - Invalidates Kite Session
Use this to test if auto-login works properly on service restart
"""
import os
import config
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def logout():
    """Invalidate access token and session"""
    logger.info("=" * 60)
    logger.info("KITE LOGOUT")
    logger.info("=" * 60)
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")
    
    token_path = os.path.join(config.BASE_DIR, "access_token.txt")
    
    # Check if token exists
    if not os.path.exists(token_path):
        logger.warning("⚠️  No access token found - already logged out")
        logger.info("")
        return
    
    # Try to invalidate session with Kite API
    try:
        from kiteconnect import KiteConnect
        
        # Read current token
        with open(token_path, 'r') as f:
            access_token = f.read().strip()
        
        if access_token:
            logger.info("Invalidating session with Kite API...")
            kite = KiteConnect(api_key=config.API_KEY)
            kite.set_access_token(access_token)
            
            # Invalidate the session
            kite.invalidate_access_token()
            logger.info("✅ Session invalidated on Kite servers")
        
    except Exception as e:
        logger.warning(f"Could not invalidate session on Kite: {e}")
        logger.info("(This is normal if token was already expired)")
    
    # Delete local token file
    try:
        os.remove(token_path)
        logger.info("✅ Access token file deleted")
    except Exception as e:
        logger.error(f"Failed to delete token file: {e}")
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ LOGOUT COMPLETE")
    logger.info("=" * 60)
    logger.info("")
    logger.info("To test auto-login:")
    logger.info("  1. Restart the service: sudo systemctl restart kite-trading-bot")
    logger.info("  2. Watch logs: sudo journalctl -u kite-trading-bot -f")
    logger.info("  3. Check if auto-login runs and generates new token")
    logger.info("")
    logger.info("Or test manually:")
    logger.info("  python auto_login.py")
    logger.info("")
    
    # Send Telegram notification
    try:
        from notifier import notifier
        notifier.send_message(
            f"🚪 **Logged Out**\n\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}\n"
            f"Access token invalidated.\n\n"
            f"Service will auto-login on next restart."
        )
    except Exception as e:
        logger.warning(f"Could not send Telegram notification: {e}")

if __name__ == "__main__":
    logout()
