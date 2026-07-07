"""Auto-login Celery worker for automated Kite re-authentication.

Schedules and executes daily Selenium-based auto-login for users
with auto-login enabled. Uses the existing auto_login.py flow
adapted for per-user execution with encrypted TOTP keys.

Requirements covered:
- 4.5: Schedule automated re-authentication daily before market open (8:45 AM IST)
- 4.8: Display the last auto-login attempt result (timestamp, success/failure)
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Database URL from environment
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/trading_platform",
)

# Module-level engine/session factory (lazy init)
_engine = None
_SessionFactory = None


def _get_session_factory():
    """Get or create the SQLAlchemy session factory (lazy singleton).

    Returns:
        A sessionmaker bound to the database engine.
    """
    global _engine, _SessionFactory
    if _SessionFactory is None:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        _SessionFactory = sessionmaker(bind=_engine)
    return _SessionFactory


def get_db_session() -> Session:
    """Create a new database session.

    Returns:
        A new SQLAlchemy Session instance.
    """
    factory = _get_session_factory()
    return factory()


def get_auto_login_users(db_session: Session) -> List[Dict]:
    """Query database for all users with auto-login enabled and a TOTP key stored.

    An auto-login eligible user is one where:
    - broker_type is "kite"
    - auto_login_enabled is True
    - totp_key_encrypted is not None

    Args:
        db_session: SQLAlchemy session for database queries.

    Returns:
        List of dicts with user_id for each eligible user.
    """
    from src.database.models.broker_connection import BrokerConnection

    try:
        connections = (
            db_session.query(BrokerConnection)
            .filter(
                BrokerConnection.broker_type == "kite",
                BrokerConnection.auto_login_enabled == True,  # noqa: E712
                BrokerConnection.totp_key_encrypted.isnot(None),
            )
            .all()
        )

        return [{"user_id": conn.user_id} for conn in connections]
    except Exception as e:
        logger.error(
            "Failed to query auto-login users: %s: %s", type(e).__name__, str(e)
        )
        return []


@celery_app.task(name="src.workers.auto_login_worker.execute_auto_login")
def execute_auto_login(user_id: int) -> dict:
    """Execute automated Kite login for a specific user.

    Steps:
    1. Decrypt stored TOTP key
    2. Run Selenium-based login flow (from existing auto_login.py)
    3. Store new access token (encrypted)
    4. Record attempt result (timestamp + status)

    Requirements covered:
    - 4.5: Automated re-authentication before market open
    - 4.8: Record last auto-login attempt result

    Args:
        user_id: The user's database ID.

    Returns:
        dict with keys: success (bool), timestamp (str), error (str|None)
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        return _execute_auto_login_impl(user_id, timestamp)
    except Exception as e:
        logger.error(
            "Unexpected top-level error in execute_auto_login for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        # Record failure in database
        _record_auto_login_result(user_id, success=False)
        return {
            "success": False,
            "timestamp": timestamp,
            "error": f"Unexpected error: {type(e).__name__}: {str(e)}",
        }


def _execute_auto_login_impl(user_id: int, timestamp: str) -> dict:
    """Internal implementation of the auto-login execution.

    Separated from the task function to allow clean error handling.
    """
    from src.broker.token_encryption import TokenEncryption
    from src.database.models.broker_connection import BrokerConnection

    db_session = get_db_session()
    try:
        # Step 1: Get user's Kite connection and decrypt TOTP key
        connection = (
            db_session.query(BrokerConnection)
            .filter(
                BrokerConnection.user_id == user_id,
                BrokerConnection.broker_type == "kite",
            )
            .first()
        )

        if connection is None:
            return {
                "success": False,
                "timestamp": timestamp,
                "error": "No Kite connection found for user",
            }

        if not connection.totp_key_encrypted:
            return {
                "success": False,
                "timestamp": timestamp,
                "error": "No TOTP key configured",
            }

        if not connection.auto_login_enabled:
            return {
                "success": False,
                "timestamp": timestamp,
                "error": "Auto-login is not enabled",
            }

        # Decrypt the TOTP key
        encryption_key = os.environ.get("ENCRYPTION_KEY", "")
        if not encryption_key:
            return {
                "success": False,
                "timestamp": timestamp,
                "error": "Encryption key not configured",
            }

        token_encryption = TokenEncryption(encryption_key=encryption_key)
        totp_key = token_encryption.decrypt(connection.totp_key_encrypted)

        # Step 2: Run Selenium-based login flow
        api_key = os.environ.get("KITE_API_KEY", "")
        api_secret = os.environ.get("KITE_API_SECRET", "")
        kite_user_id = os.environ.get("KITE_USER_ID", "")
        kite_password = os.environ.get("KITE_PASSWORD", "")

        if not api_key or not api_secret:
            return {
                "success": False,
                "timestamp": timestamp,
                "error": "Broker API credentials not configured",
            }

        access_token = _run_login_flow(
            api_key=api_key,
            api_secret=api_secret,
            kite_user_id=kite_user_id,
            kite_password=kite_password,
            totp_key=totp_key,
        )

        if not access_token:
            # Record failure
            _record_auto_login_result(user_id, success=False)
            return {
                "success": False,
                "timestamp": timestamp,
                "error": "Login flow failed to obtain access token",
            }

        # Step 3: Store new access token (encrypted)
        encrypted_token = token_encryption.encrypt(access_token)
        token_expiry = datetime.now(timezone.utc) + timedelta(hours=24)

        connection.access_token_encrypted = encrypted_token
        connection.token_expiry = token_expiry
        connection.status = "connected"
        connection.error_message = None

        # Step 4: Record success result
        connection.last_auto_login_at = datetime.now(timezone.utc)
        connection.last_auto_login_success = True

        db_session.commit()

        # Step 5: Also save to access_token.txt for Telegram bot compatibility
        _save_shared_token(access_token)

        logger.info(
            "Auto-login successful for user %d, token expires %s",
            user_id,
            token_expiry.isoformat(),
        )

        return {
            "success": True,
            "timestamp": timestamp,
            "error": None,
        }

    except Exception as e:
        db_session.rollback()
        logger.error(
            "Auto-login failed for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
            exc_info=True,
        )
        # Record failure
        _record_auto_login_result(user_id, success=False)
        return {
            "success": False,
            "timestamp": timestamp,
            "error": f"{type(e).__name__}: {str(e)}",
        }
    finally:
        db_session.close()


def _run_login_flow(
    api_key: str,
    api_secret: str,
    kite_user_id: str,
    kite_password: str,
    totp_key: str,
) -> str | None:
    """Run the Selenium-based Kite login flow and return the access token.

    Uses the existing AutoLogin class from auto_login.py adapted for
    programmatic invocation with explicit credentials.

    Args:
        api_key: Kite API key.
        api_secret: Kite API secret.
        kite_user_id: Kite user ID for login.
        kite_password: Kite password for login.
        totp_key: Decrypted TOTP secret key.

    Returns:
        The access token string on success, None on failure.
    """
    try:
        from auto_login import AutoLogin

        # Create AutoLogin instance and override credentials
        auto_login = AutoLogin(headless=True)
        auto_login.api_key = api_key
        auto_login.api_secret = api_secret
        auto_login.user_id = kite_user_id
        auto_login.password = kite_password
        auto_login.totp_key = totp_key

        try:
            # Setup browser
            auto_login.setup_driver()

            # Login and get request token
            request_token = auto_login.login_to_kite()
            if not request_token:
                logger.error("Auto-login: failed to obtain request token")
                return None

            # Generate access token from request token
            access_token = auto_login.generate_access_token(request_token)
            if not access_token:
                logger.error("Auto-login: failed to generate access token")
                return None

            return access_token
        finally:
            auto_login.close()

    except ImportError:
        logger.error(
            "auto_login module not available. "
            "Falling back to API-based login."
        )
        return _run_api_login_flow(api_key, api_secret, totp_key)
    except Exception as e:
        logger.error("Selenium login flow failed: %s: %s", type(e).__name__, str(e))
        return None


def _run_api_login_flow(
    api_key: str, api_secret: str, totp_key: str
) -> str | None:
    """Fallback: attempt login via Kite Connect API with TOTP.

    This is a placeholder for environments where Selenium is not available.
    Uses the kiteconnect library to generate a session if a request_token
    can be obtained through other means.

    Args:
        api_key: Kite API key.
        api_secret: Kite API secret.
        totp_key: Decrypted TOTP secret key.

    Returns:
        The access token string on success, None on failure.
    """
    import pyotp

    try:
        totp = pyotp.TOTP(totp_key)
        code = totp.now()
        logger.info("Generated TOTP code for API-based login: %s", code[:2] + "****")

        # The Kite Connect API doesn't support direct TOTP-based login
        # without the Selenium flow. This is a placeholder for future
        # API-based authentication support.
        logger.warning(
            "API-based login not fully implemented. "
            "Selenium-based login (auto_login.py) is required."
        )
        return None

    except Exception as e:
        logger.error("API login flow failed: %s: %s", type(e).__name__, str(e))
        return None


def _save_shared_token(access_token: str) -> None:
    """Save access token to access_token.txt for Telegram bot compatibility.

    Both the web platform (reads from DB) and the Telegram bot (reads from file)
    will have access to the same valid token.

    Args:
        access_token: The plaintext access token to save.
    """
    try:
        # Determine the project root (where access_token.txt lives)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        token_path = os.path.join(project_root, "access_token.txt")

        with open(token_path, "w") as f:
            f.write(access_token)

        logger.info("Shared access token saved to: %s", token_path)
    except Exception as e:
        # Non-fatal — web app still has the token in DB
        logger.warning("Failed to save shared access_token.txt: %s", str(e))


def _record_auto_login_result(user_id: int, success: bool) -> None:
    """Record the auto-login attempt result in the database.

    Updates last_auto_login_at and last_auto_login_success fields
    on the user's Kite broker connection.

    Args:
        user_id: The user's database ID.
        success: Whether the auto-login attempt succeeded.
    """
    from src.database.models.broker_connection import BrokerConnection

    db_session = get_db_session()
    try:
        connection = (
            db_session.query(BrokerConnection)
            .filter(
                BrokerConnection.user_id == user_id,
                BrokerConnection.broker_type == "kite",
            )
            .first()
        )

        if connection:
            connection.last_auto_login_at = datetime.now(timezone.utc)
            connection.last_auto_login_success = success
            db_session.commit()
    except Exception as e:
        logger.error(
            "Failed to record auto-login result for user %d: %s: %s",
            user_id,
            type(e).__name__,
            str(e),
        )
        db_session.rollback()
    finally:
        db_session.close()


@celery_app.task(name="src.workers.auto_login_worker.schedule_auto_logins")
def schedule_auto_logins() -> dict:
    """Celery beat task: Dispatch execute_auto_login for all eligible users.

    Queries the database for all users with auto_login_enabled=True
    and a stored TOTP key, then dispatches individual execute_auto_login
    tasks for each.

    Skips execution on weekends since markets are closed.

    Requirements covered:
    - 4.5: Schedule automated re-authentication daily before market open

    Returns:
        dict with keys: status (str), users_dispatched (int), reason (str)
    """
    try:
        return _execute_schedule_auto_logins()
    except Exception as e:
        logger.error(
            "Unexpected top-level error in schedule_auto_logins: %s: %s",
            type(e).__name__,
            str(e),
        )
        return {
            "status": "error",
            "users_dispatched": 0,
            "reason": f"Unexpected error: {type(e).__name__}: {str(e)}",
        }


def _execute_schedule_auto_logins() -> dict:
    """Internal implementation of the auto-login scheduler.

    Queries eligible users and dispatches individual auto-login tasks.
    """
    from zoneinfo import ZoneInfo

    # Skip weekends
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    if now_ist.weekday() >= 5:  # Saturday=5, Sunday=6
        logger.info("Weekend detected, skipping auto-login scheduling")
        return {
            "status": "skipped",
            "users_dispatched": 0,
            "reason": "Weekend - markets closed",
        }

    db_session = get_db_session()
    try:
        eligible_users = get_auto_login_users(db_session)

        if not eligible_users:
            logger.info("No users with auto-login enabled")
            return {
                "status": "success",
                "users_dispatched": 0,
                "reason": "No users with auto-login enabled",
            }

        # Dispatch an execute_auto_login task for each eligible user
        dispatched_count = 0
        for user_info in eligible_users:
            user_id = user_info["user_id"]
            try:
                execute_auto_login.delay(user_id)
                dispatched_count += 1
                logger.info("Dispatched auto-login task for user %d", user_id)
            except Exception as e:
                logger.error(
                    "Failed to dispatch auto-login for user %d: %s: %s",
                    user_id,
                    type(e).__name__,
                    str(e),
                )

        logger.info(
            "Auto-login scheduled: dispatched %d/%d user tasks",
            dispatched_count,
            len(eligible_users),
        )

        return {
            "status": "success",
            "users_dispatched": dispatched_count,
            "reason": f"Dispatched {dispatched_count} auto-login tasks",
        }
    finally:
        db_session.close()
