import logging
import os
from kiteconnect import KiteConnect
import config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_kite_session():
    """
    Initializes and returns a KiteConnect session.
    It tries to read a saved access_token. If invalid or missing,
    it re-authenticates (assumes manual intervention or existing valid token logic).
    
    For fully automated login (bypass TOTP), external libraries like `kiteext` 
    or manual daily login is required. Here we implement the standard flow 
    which expects a valid 'access_token.txt' or manual Login flow.
    """
    kite = KiteConnect(api_key=config.API_KEY)

    # Try to load existing access token
    if os.path.exists(config.ACCESS_TOKEN_PATH):
        with open(config.ACCESS_TOKEN_PATH, 'r') as f:
            access_token = f.read().strip()
            if access_token:
                kite.set_access_token(access_token)
                try:
                    # Verify token validity
                    kite.profile()
                    logger.info("Session verified with existing access token.")
                    return kite
                except Exception as e:
                    logger.warning(f"Existing access token invalid: {e}")

    # If we are here, we need a new session
    # In a real deployed bot, you'd likely use a generated request token 
    # from a login URL or a selenium script to get it automatically.
    # For now, we will print the login URL if this fails.
    
    logger.error("Valid access token not found. Please generate a new one.")
    print("Login URL:", kite.login_url())
    # TODO: Implement Totp or Selenium automation if user requests valid fully automated login
    # For now, returning kite object (un-authenticated) so standard error can be thrown later
    # or user can fix it.
    
    return kite

def save_access_token(access_token):
    with open(config.ACCESS_TOKEN_PATH, 'w') as f:
        f.write(access_token)
    logger.info("Access token saved.")
