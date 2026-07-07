"""Broker integration module for the Multi-User Web Trading Platform.

Provides Zerodha Kite Connect integration with OAuth flow,
token encryption/decryption, token lifecycle management,
and user-specific Kite client factory.

Requirements covered:
- 1.2.1: Integrate with Zerodha Kite Connect API
- 1.2.2: Support OAuth-based broker authentication
- 1.2.3: Encrypt broker access tokens before storing in database
- 1.2.4: Automatically refresh broker tokens before expiry
- 1.2.5: Notify users when broker token refresh fails
- 2.4.4: Encrypt broker tokens using Fernet
"""

from src.broker.token_encryption import TokenEncryption, TokenEncryptionError
from src.broker.oauth import ZerodhaOAuth, OAuthError
from src.broker.kite_client_factory import (
    KiteClientFactory,
    BrokerAuthError,
    TokenExpiredError,
)
from src.broker.token_refresh import TokenRefreshService, TokenRefreshError

__all__ = [
    "TokenEncryption",
    "TokenEncryptionError",
    "ZerodhaOAuth",
    "OAuthError",
    "KiteClientFactory",
    "BrokerAuthError",
    "TokenExpiredError",
    "TokenRefreshService",
    "TokenRefreshError",
]
