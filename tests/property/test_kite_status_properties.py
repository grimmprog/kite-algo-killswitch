"""Property-based tests for Kite connection status derivation (Task 2.2).

Uses Hypothesis to verify:
- Property 1: Kite Connection Status Derivation — every combination of token
  presence and expiry state produces exactly one valid status.

**Validates: Requirements 2.1, 2.3, 2.4, 2.5**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from datetime import datetime, timedelta, timezone

from hypothesis import given, strategies as st, settings, assume

from src.services.broker_settings_service import derive_kite_status


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Token can be None, empty string, or arbitrary non-empty string
token_strategy = st.one_of(
    st.none(),
    st.just(""),
    st.text(min_size=1, max_size=200),
)

# Past datetimes: 1 second to 365 days in the past (always UTC-aware)
past_datetime_strategy = st.floats(
    min_value=1.0, max_value=365 * 24 * 3600.0,
    allow_nan=False, allow_infinity=False,
).map(lambda secs: datetime.now(timezone.utc) - timedelta(seconds=secs))

# Future datetimes: 1 second to 365 days in the future (always UTC-aware)
future_datetime_strategy = st.floats(
    min_value=1.0, max_value=365 * 24 * 3600.0,
    allow_nan=False, allow_infinity=False,
).map(lambda secs: datetime.now(timezone.utc) + timedelta(seconds=secs))

# Expiry can be None, past datetime, or future datetime
expiry_strategy = st.one_of(
    st.none(),
    past_datetime_strategy,
    future_datetime_strategy,
)

VALID_STATUSES = {"Connected", "Disconnected", "Token Expired"}


# ============================================================
# Property 1: Kite Connection Status Derivation
# ============================================================


class TestKiteConnectionStatusDerivation:
    """Property-based tests for derive_kite_status function.

    **Validates: Requirements 2.1, 2.3, 2.4, 2.5**

    Core invariants:
    - The function always returns exactly one of: "Connected", "Disconnected", "Token Expired"
    - No token (None or empty) → "Disconnected"
    - Token present + expiry in future → "Connected"
    - Token present + expiry in past → "Token Expired"
    - Token present + no expiry (None) → "Disconnected"
    """

    @given(token=token_strategy, expiry=expiry_strategy)
    @settings(max_examples=200, deadline=None)
    def test_status_is_always_one_of_three_valid_values(self, token, expiry):
        """derive_kite_status always returns exactly one valid status string.

        **Validates: Requirements 2.1**

        Property: For any combination of token_encrypted and token_expiry,
        the result is always in {"Connected", "Disconnected", "Token Expired"}.
        """
        result = derive_kite_status(token, expiry)
        assert result in VALID_STATUSES, (
            f"Expected one of {VALID_STATUSES}, got '{result}' "
            f"for token={token!r}, expiry={expiry!r}"
        )

    @given(
        expiry=expiry_strategy,
        token=st.one_of(st.none(), st.just("")),
    )
    @settings(max_examples=100, deadline=None)
    def test_no_token_returns_disconnected(self, token, expiry):
        """No token (None or empty string) always yields "Disconnected".

        **Validates: Requirements 2.5**

        Property: For any expiry value, if token_encrypted is None or "",
        derive_kite_status returns "Disconnected".
        """
        result = derive_kite_status(token, expiry)
        assert result == "Disconnected", (
            f"Expected 'Disconnected' for no token, got '{result}' "
            f"with token={token!r}, expiry={expiry!r}"
        )

    @given(
        token=st.text(min_size=1, max_size=200),
        expiry=future_datetime_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_token_with_future_expiry_returns_connected(self, token, expiry):
        """Token present with future expiry yields "Connected".

        **Validates: Requirements 2.3**

        Property: For any non-empty token and expiry datetime in the future,
        derive_kite_status returns "Connected".
        """
        result = derive_kite_status(token, expiry)
        assert result == "Connected", (
            f"Expected 'Connected' for valid token with future expiry, got '{result}' "
            f"with token={token!r}, expiry={expiry!r}"
        )

    @given(
        token=st.text(min_size=1, max_size=200),
        expiry=past_datetime_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_token_with_past_expiry_returns_token_expired(self, token, expiry):
        """Token present with past expiry yields "Token Expired".

        **Validates: Requirements 2.4**

        Property: For any non-empty token and expiry datetime in the past,
        derive_kite_status returns "Token Expired".
        """
        result = derive_kite_status(token, expiry)
        assert result == "Token Expired", (
            f"Expected 'Token Expired' for token with past expiry, got '{result}' "
            f"with token={token!r}, expiry={expiry!r}"
        )

    @given(token=st.text(min_size=1, max_size=200))
    @settings(max_examples=100, deadline=None)
    def test_token_with_no_expiry_returns_disconnected(self, token):
        """Token present with no expiry (None) yields "Disconnected".

        **Validates: Requirements 2.5**

        Property: For any non-empty token and expiry=None,
        derive_kite_status returns "Disconnected".
        """
        result = derive_kite_status(token, None)
        assert result == "Disconnected", (
            f"Expected 'Disconnected' for token with no expiry, got '{result}' "
            f"with token={token!r}"
        )
