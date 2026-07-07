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
    
    Token resolution order:
    1. Read from access_token.txt (shared between Telegram bot and web app)
    2. If invalid, try to read from the web app's database (broker_connections table)
    3. If both fail, prompt for manual login
    
    Both the Telegram bot and web platform write to access_token.txt after auto-login,
    ensuring a single shared Kite session.
    """
    kite = KiteConnect(api_key=config.API_KEY)

    # Try to load existing access token from file
    if os.path.exists(config.ACCESS_TOKEN_PATH):
        with open(config.ACCESS_TOKEN_PATH, 'r') as f:
            access_token = f.read().strip()
            if access_token:
                kite.set_access_token(access_token)
                try:
                    # Verify token validity
                    kite.profile()
                    logger.info("✅ Session verified with existing access token from file.")
                    return kite
                except Exception as e:
                    logger.warning(f"File access token invalid: {e}")

    # Try to read from database (web platform's encrypted store)
    db_token = _get_token_from_database()
    if db_token:
        kite.set_access_token(db_token)
        try:
            kite.profile()
            logger.info("✅ Session verified with database access token.")
            # Sync back to file for Telegram bot
            save_access_token(db_token)
            return kite
        except Exception as e:
            logger.warning(f"Database access token invalid: {e}")

    # If we are here, we need a new session via auto-login
    logger.warning("No valid access token found. Attempting auto-login...")
    
    try:
        from auto_login import AutoLogin
        auto_login = AutoLogin(headless=True)
        success = auto_login.run()
        
        if success and os.path.exists(config.ACCESS_TOKEN_PATH):
            with open(config.ACCESS_TOKEN_PATH, 'r') as f:
                access_token = f.read().strip()
            if access_token:
                kite.set_access_token(access_token)
                # Also store in database for web app
                _store_token_in_database(access_token)
                logger.info("✅ Auto-login successful, session established.")
                return kite
    except Exception as e:
        logger.error(f"Auto-login failed: {e}")
    
    logger.error("❌ Could not establish Kite session. Manual login required.")
    print("Login URL:", kite.login_url())
    return kite


def _get_token_from_database() -> str | None:
    """Try to read a valid access token from the web platform's database.
    
    Returns:
        Decrypted access token string, or None if not available.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        db_url = os.environ.get("DATABASE_URL")
        encryption_key = os.environ.get("ENCRYPTION_KEY")
        
        if not db_url or not encryption_key:
            return None
        
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from src.database.models.broker_connection import BrokerConnection
        from src.broker.token_encryption import TokenEncryption
        from datetime import datetime, timezone
        
        engine = create_engine(db_url)
        with Session(engine) as session:
            # Find any Kite connection with a valid (non-expired) token
            connection = (
                session.query(BrokerConnection)
                .filter(
                    BrokerConnection.broker_type == "kite",
                    BrokerConnection.access_token_encrypted.isnot(None),
                    BrokerConnection.token_expiry > datetime.now(timezone.utc),
                )
                .first()
            )
            
            if connection:
                encryptor = TokenEncryption(encryption_key=encryption_key)
                return encryptor.decrypt(connection.access_token_encrypted)
        
        return None
    except Exception as e:
        logger.debug(f"Could not read token from database: {e}")
        return None


def _store_token_in_database(access_token: str) -> None:
    """Store access token in the web platform's database for sharing.
    
    Encrypts and stores the token in broker_connections for the first user
    (admin user) so the web app can use it.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        db_url = os.environ.get("DATABASE_URL")
        encryption_key = os.environ.get("ENCRYPTION_KEY")
        
        if not db_url or not encryption_key:
            return
        
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from src.database.models.broker_connection import BrokerConnection
        from src.broker.token_encryption import TokenEncryption
        from datetime import datetime, timedelta, timezone
        
        engine = create_engine(db_url)
        encryptor = TokenEncryption(encryption_key=encryption_key)
        encrypted_token = encryptor.encrypt(access_token)
        token_expiry = datetime.now(timezone.utc) + timedelta(hours=24)
        
        with Session(engine) as session:
            # Update or create for admin user (id=1)
            connection = (
                session.query(BrokerConnection)
                .filter(
                    BrokerConnection.user_id == 1,
                    BrokerConnection.broker_type == "kite",
                )
                .first()
            )
            
            if connection:
                connection.access_token_encrypted = encrypted_token
                connection.token_expiry = token_expiry
                connection.status = "connected"
                connection.error_message = None
            else:
                connection = BrokerConnection(
                    user_id=1,
                    broker_type="kite",
                    access_token_encrypted=encrypted_token,
                    token_expiry=token_expiry,
                    status="connected",
                )
                session.add(connection)
            
            session.commit()
            logger.info("Access token synced to database for web platform.")
    except Exception as e:
        logger.debug(f"Could not store token in database: {e}")


def save_access_token(access_token):
    """Save access token to file (shared between bot and web app)."""
    with open(config.ACCESS_TOKEN_PATH, 'w') as f:
        f.write(access_token)
    logger.info("Access token saved to file.")
