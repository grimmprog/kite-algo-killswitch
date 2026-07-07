"""Fernet-based token encryption for broker credentials.

Requirements covered:
- 1.2.3: Encrypt broker access tokens before storing in database
- 2.4.4: Encrypt broker tokens in database using Fernet
- 2.4.5: Never log or expose broker tokens in API responses
"""

import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class TokenEncryptionError(Exception):
    """Raised when token encryption or decryption fails."""
    pass


class TokenEncryption:
    """Fernet-based symmetric encryption for broker tokens.

    Uses the cryptography library's Fernet implementation which provides
    authenticated encryption (AES-128-CBC with HMAC-SHA256).

    The encryption key must be a valid Fernet key (32 url-safe base64-encoded bytes).
    Generate one with: `from cryptography.fernet import Fernet; Fernet.generate_key()`
    """

    def __init__(self, encryption_key: str):
        """Initialize with Fernet key.

        Args:
            encryption_key: A valid Fernet key string (from ENCRYPTION_KEY env var).
                Must be 32 url-safe base64-encoded bytes.

        Raises:
            ValueError: If encryption_key is empty or invalid.
        """
        if not encryption_key:
            raise ValueError("Encryption key cannot be empty")

        try:
            # Fernet expects bytes
            if isinstance(encryption_key, str):
                encryption_key = encryption_key.encode()
            self._fernet = Fernet(encryption_key)
        except Exception as e:
            raise ValueError(f"Invalid Fernet encryption key: {e}")

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a token string.

        Args:
            plaintext: The plaintext token to encrypt.

        Returns:
            The encrypted token as a base64-encoded string.

        Raises:
            TokenEncryptionError: If encryption fails.
            ValueError: If plaintext is empty.
        """
        if not plaintext:
            raise ValueError("Cannot encrypt empty string")

        try:
            encrypted = self._fernet.encrypt(plaintext.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error("Token encryption failed")
            raise TokenEncryptionError(f"Encryption failed: {e}")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a token string.

        Args:
            ciphertext: The encrypted token (base64-encoded string).

        Returns:
            The decrypted plaintext token.

        Raises:
            TokenEncryptionError: If decryption fails (invalid key or corrupted data).
            ValueError: If ciphertext is empty.
        """
        if not ciphertext:
            raise ValueError("Cannot decrypt empty string")

        try:
            decrypted = self._fernet.decrypt(ciphertext.encode())
            return decrypted.decode()
        except InvalidToken:
            logger.error("Token decryption failed: invalid token or key mismatch")
            raise TokenEncryptionError(
                "Decryption failed: invalid token or wrong encryption key"
            )
        except Exception as e:
            logger.error("Token decryption failed")
            raise TokenEncryptionError(f"Decryption failed: {e}")

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet encryption key.

        Returns:
            A new valid Fernet key as a string.
        """
        return Fernet.generate_key().decode()
