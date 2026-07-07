"""Rate limiting for login attempts.

Requirements covered:
- 2.4.8: Rate limit login attempts (5 attempts per 15 minutes)
"""

from typing import Optional


class LoginRateLimiter:
    """Rate limit login attempts: 5 attempts per 15 minutes per email.

    Uses Redis to track login attempts with a sliding window approach.
    Each email gets a key that stores the number of attempts with a TTL
    equal to the window duration.
    """

    DEFAULT_MAX_ATTEMPTS = 5
    DEFAULT_WINDOW_SECONDS = 900  # 15 minutes

    def __init__(
        self,
        redis_client,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ):
        """Initialize the rate limiter.

        Args:
            redis_client: Redis client instance.
            max_attempts: Maximum number of login attempts allowed in the window.
            window_seconds: Duration of the rate limiting window in seconds.

        Raises:
            ValueError: If max_attempts or window_seconds are not positive.
        """
        if max_attempts <= 0:
            raise ValueError("max_attempts must be a positive integer")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be a positive integer")

        self.redis_client = redis_client
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds

    def _get_key(self, email: str) -> str:
        """Generate Redis key for tracking login attempts.

        Args:
            email: The user's email address.

        Returns:
            Redis key string.
        """
        return f"login_attempts:{email}"

    def check_rate_limit(self, email: str) -> bool:
        """Check if the email is allowed to attempt login.

        Returns True if the number of attempts is below the limit,
        False if rate limited.

        Args:
            email: The user's email address.

        Returns:
            True if allowed, False if rate limited.
        """
        key = self._get_key(email)
        attempts = self.redis_client.get(key)

        if attempts is None:
            return True

        return int(attempts) < self.max_attempts

    def record_attempt(self, email: str) -> None:
        """Record a login attempt for the given email.

        Increments the attempt counter. If this is the first attempt,
        sets the TTL for the window duration.

        Args:
            email: The user's email address.
        """
        key = self._get_key(email)
        pipe = self.redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, self.window_seconds)
        pipe.execute()

    def reset(self, email: str) -> None:
        """Reset the rate limit counter for the given email.

        Called after a successful login to clear the attempt counter.

        Args:
            email: The user's email address.
        """
        key = self._get_key(email)
        self.redis_client.delete(key)

    def get_remaining_attempts(self, email: str) -> int:
        """Get the number of remaining login attempts.

        Args:
            email: The user's email address.

        Returns:
            Number of remaining attempts.
        """
        key = self._get_key(email)
        attempts = self.redis_client.get(key)

        if attempts is None:
            return self.max_attempts

        return max(0, self.max_attempts - int(attempts))

    def get_ttl(self, email: str) -> Optional[int]:
        """Get the time remaining until the rate limit window resets.

        Args:
            email: The user's email address.

        Returns:
            Seconds until reset, or None if no active limit.
        """
        key = self._get_key(email)
        ttl = self.redis_client.ttl(key)

        if ttl <= 0:
            return None

        return ttl
