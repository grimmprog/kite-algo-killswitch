"""Custom authentication exceptions.

Requirements covered:
- 1.1.10: Support user logout and token invalidation
- 2.4.8: Rate limit login attempts
"""


class AuthenticationError(Exception):
    """Raised when authentication fails.

    This includes invalid credentials, expired tokens,
    or rate-limited login attempts.
    """

    def __init__(self, message: str = "Authentication failed"):
        self.message = message
        super().__init__(self.message)
