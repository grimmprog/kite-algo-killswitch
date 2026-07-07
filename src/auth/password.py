"""Password hashing and verification using bcrypt.

Requirements covered:
- 1.1.2: Password hashing using bcrypt with cost factor 12
- 1.1.3: Minimum password length of 8 characters
"""

import bcrypt

BCRYPT_COST_FACTOR = 12
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    """Hash password using bcrypt with cost factor 12.

    Args:
        password: The plaintext password to hash.

    Returns:
        The bcrypt hash string.

    Raises:
        ValueError: If password is less than 8 characters or exceeds 72 bytes.
    """
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )

    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        raise ValueError("Password cannot exceed 72 bytes when UTF-8 encoded")

    salt = bcrypt.gensalt(rounds=BCRYPT_COST_FACTOR)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its bcrypt hash.

    Args:
        password: The plaintext password to verify.
        password_hash: The bcrypt hash to verify against.

    Returns:
        True if the password matches the hash, False otherwise.
    """
    if not password or not password_hash:
        return False

    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8"),
    )
