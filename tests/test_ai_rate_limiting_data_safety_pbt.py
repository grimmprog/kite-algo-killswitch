"""Property-based tests for AI Rate Limiting and Data Safety.

**Validates: Requirements 17.3, 17.5**

Property 16: AI Rate Limiting — Verify max 30 requests per 60-second rolling window.
Property 17: AI Data Safety — Verify no credentials/PII in AI API payloads.

Uses Hypothesis for property-based testing with pytest.
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hypothesis import given, settings, assume, note
from hypothesis import strategies as st

from src.services.ai_trading_service import (
    AITradingService,
    AIProvider,
    TokenBucketRateLimiter,
    SENSITIVE_FIELDS,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for generating sensitive key names (from the actual SENSITIVE_FIELDS set)
sensitive_keys_st = st.sampled_from(sorted(SENSITIVE_FIELDS))

# Strategy for generating safe/non-sensitive key names that won't collide
safe_keys_st = st.sampled_from([
    "symbol", "entry_price", "stop_loss", "target_price", "confidence_score",
    "ema_20", "vwap", "macd", "rsi", "volume", "trend_direction",
    "timeframe", "candle_count", "open", "high", "low", "close",
    "momentum_score", "volume_score", "composite_score", "range_high",
    "range_low", "avg_price", "breakout_price", "duration_minutes",
])

# Strategy for safe values (non-dict primitives)
safe_values_st = st.one_of(
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    st.integers(min_value=-1000000, max_value=1000000),
    st.text(min_size=0, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"))),
    st.booleans(),
)

# Strategy for sensitive values (things that look like credentials/PII)
sensitive_values_st = st.one_of(
    st.text(min_size=1, max_size=64, alphabet=st.characters(whitelist_categories=("L", "N"))),
    st.emails(),
    st.from_regex(r"[0-9]{10}", fullmatch=True),  # phone-like
)


def nested_payload_st(max_depth=3):
    """Strategy to generate arbitrarily nested payloads with both safe and sensitive keys."""
    if max_depth <= 0:
        return st.dictionaries(
            keys=st.one_of(sensitive_keys_st, safe_keys_st),
            values=safe_values_st,
            min_size=1,
            max_size=5,
        )

    leaf_values = st.one_of(safe_values_st, sensitive_values_st)

    recursive_values = st.one_of(
        leaf_values,
        st.dictionaries(
            keys=st.one_of(sensitive_keys_st, safe_keys_st),
            values=leaf_values,
            min_size=1,
            max_size=3,
        ),
    )

    return st.dictionaries(
        keys=st.one_of(sensitive_keys_st, safe_keys_st),
        values=recursive_values,
        min_size=1,
        max_size=8,
    )


# Strategy for payloads that contain at least one sensitive field
payload_with_sensitive_st = st.builds(
    lambda safe_dict, sens_key, sens_val: {**safe_dict, sens_key: sens_val},
    safe_dict=st.dictionaries(
        keys=safe_keys_st,
        values=safe_values_st,
        min_size=1,
        max_size=5,
    ),
    sens_key=sensitive_keys_st,
    sens_val=sensitive_values_st,
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def contains_sensitive_key(d: dict) -> bool:
    """Recursively check if any key in the dict (or nested dicts) is sensitive."""
    for key, value in d.items():
        if key.lower() in SENSITIVE_FIELDS:
            return True
        if isinstance(value, dict):
            if contains_sensitive_key(value):
                return True
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and contains_sensitive_key(item):
                    return True
    return False


def all_keys_recursive(d: dict) -> set:
    """Get all keys recursively from a nested dict structure."""
    keys = set()
    for key, value in d.items():
        keys.add(key.lower())
        if isinstance(value, dict):
            keys.update(all_keys_recursive(value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    keys.update(all_keys_recursive(item))
    return keys


# ---------------------------------------------------------------------------
# Property 16: AI Rate Limiting
# ---------------------------------------------------------------------------


class TestProperty16AIRateLimiting:
    """Property 16: AI Rate Limiting — Verify max 30 requests per 60-second rolling window.

    **Validates: Requirements 17.3**

    The token bucket rate limiter allows at most max_tokens (30) requests
    in a burst. After tokens are exhausted, requests are rejected until
    tokens refill. With refill_rate=0.5 tokens/sec, it takes 60 seconds
    to refill all 30 tokens.
    """

    @given(
        num_requests=st.integers(min_value=31, max_value=100),
    )
    @settings(max_examples=50)
    def test_burst_limited_to_30(self, num_requests):
        """Property: A fresh rate limiter allows exactly 30 requests, then rejects.

        **Validates: Requirements 17.3**

        For any number of requests > 30, only 30 should succeed from a
        fresh bucket (no time passing = no refill).
        """
        limiter = TokenBucketRateLimiter(max_tokens=30, refill_rate=0.5)

        successes = sum(1 for _ in range(num_requests) if limiter.consume())

        assert successes == 30, (
            f"Expected exactly 30 successful requests but got {successes} "
            f"out of {num_requests} attempts"
        )

    @given(
        max_tokens=st.integers(min_value=1, max_value=100),
        num_requests=st.integers(min_value=1, max_value=200),
    )
    @settings(max_examples=100)
    def test_never_exceeds_max_tokens(self, max_tokens, num_requests):
        """Property: Total successful consumes never exceed max_tokens from a fresh bucket.

        **Validates: Requirements 17.3**

        For any bucket size and any number of requests (without time passing),
        the number of accepted requests equals min(num_requests, max_tokens).
        """
        limiter = TokenBucketRateLimiter(max_tokens=max_tokens, refill_rate=0.5)

        successes = sum(1 for _ in range(num_requests) if limiter.consume())

        expected = min(num_requests, max_tokens)
        assert successes == expected, (
            f"Expected {expected} successes (max_tokens={max_tokens}, "
            f"requests={num_requests}) but got {successes}"
        )

    @given(
        elapsed_seconds=st.floats(min_value=0.1, max_value=120.0),
    )
    @settings(max_examples=50)
    def test_refill_respects_rate_and_cap(self, elapsed_seconds):
        """Property: After exhausting tokens, refill = min(elapsed * rate, max_tokens).

        **Validates: Requirements 17.3**

        The refill logic adds tokens at the specified rate but never exceeds
        the maximum bucket capacity.
        """
        max_tokens = 30
        refill_rate = 0.5
        limiter = TokenBucketRateLimiter(max_tokens=max_tokens, refill_rate=refill_rate)

        # Exhaust all tokens
        for _ in range(max_tokens):
            limiter.consume()

        # Simulate time passing
        limiter.last_refill_time = time.monotonic() - elapsed_seconds

        available = limiter.available_tokens
        expected = min(elapsed_seconds * refill_rate, float(max_tokens))

        # Allow small floating-point tolerance
        assert abs(available - expected) < 0.1, (
            f"After {elapsed_seconds:.2f}s, expected ~{expected:.2f} tokens "
            f"but got {available:.2f}"
        )

    @given(
        consume_count=st.integers(min_value=0, max_value=30),
    )
    @settings(max_examples=50)
    def test_partial_consumption_leaves_remainder(self, consume_count):
        """Property: After consuming N tokens, exactly (30 - N) remain available.

        **Validates: Requirements 17.3**

        The bucket accurately tracks partial consumption.
        """
        limiter = TokenBucketRateLimiter(max_tokens=30, refill_rate=0.5)

        for _ in range(consume_count):
            limiter.consume()

        # available_tokens triggers a refill, but since very little time passes
        # in a tight loop, the remaining should be close to (30 - consume_count)
        remaining = limiter.available_tokens
        expected = 30.0 - consume_count

        # Very tight timing tolerance (test runs in microseconds)
        assert abs(remaining - expected) < 0.5, (
            f"After consuming {consume_count}, expected ~{expected:.1f} "
            f"remaining but got {remaining:.2f}"
        )

    @given(
        refill_rate=st.floats(min_value=0.1, max_value=10.0),
    )
    @settings(max_examples=30)
    def test_60_second_window_refills_to_rate_times_60(self, refill_rate):
        """Property: After 60 seconds, tokens refilled = min(rate * 60, max_tokens).

        **Validates: Requirements 17.3**

        The 60-second rolling window behavior: rate * 60 gives the number
        of tokens recovered in one full minute.
        """
        max_tokens = 30
        limiter = TokenBucketRateLimiter(max_tokens=max_tokens, refill_rate=refill_rate)

        # Exhaust all tokens
        for _ in range(max_tokens):
            limiter.consume()

        # Simulate exactly 60 seconds passing
        limiter.last_refill_time = time.monotonic() - 60.0

        available = limiter.available_tokens
        expected = min(refill_rate * 60.0, float(max_tokens))

        assert abs(available - expected) < 0.5, (
            f"With refill_rate={refill_rate}, after 60s expected ~{expected:.1f} "
            f"tokens but got {available:.2f}"
        )


# ---------------------------------------------------------------------------
# Property 17: AI Data Safety
# ---------------------------------------------------------------------------


class TestProperty17AIDataSafety:
    """Property 17: AI Data Safety — Verify no credentials/PII in AI API payloads.

    **Validates: Requirements 17.5**

    The sanitize_payload method must strip ALL sensitive fields (credentials,
    PII, financial data) from any arbitrarily nested payload before it is
    sent to the AI API. No sensitive key should ever appear in the output.
    """

    def _make_service(self):
        """Create a fresh AITradingService instance."""
        return AITradingService(provider=AIProvider.GEMINI, api_key="test-key")

    @given(payload=payload_with_sensitive_st)
    @settings(max_examples=100)
    def test_no_sensitive_keys_in_output(self, payload):
        """Property: Sanitized output never contains any sensitive field keys.

        **Validates: Requirements 17.5**

        For any payload that includes sensitive keys, the sanitized output
        must have all those keys removed.
        """
        service = self._make_service()
        result = service.sanitize_payload(payload)

        output_keys = all_keys_recursive(result) if isinstance(result, dict) else set()
        leaked_keys = output_keys & SENSITIVE_FIELDS

        assert len(leaked_keys) == 0, (
            f"Sensitive keys leaked through sanitization: {leaked_keys}"
        )

    @given(payload=nested_payload_st(max_depth=3))
    @settings(max_examples=100)
    def test_nested_sanitization_removes_all_sensitive(self, payload):
        """Property: Nested payloads have ALL sensitive keys removed at every level.

        **Validates: Requirements 17.5**

        Regardless of nesting depth, no sensitive field survives sanitization.
        """
        service = self._make_service()
        result = service.sanitize_payload(payload)

        if isinstance(result, dict):
            output_keys = all_keys_recursive(result)
            leaked_keys = output_keys & SENSITIVE_FIELDS
            assert len(leaked_keys) == 0, (
                f"Sensitive keys leaked in nested payload: {leaked_keys}"
            )

    @given(
        safe_payload=st.dictionaries(
            keys=safe_keys_st,
            values=safe_values_st,
            min_size=1,
            max_size=10,
        )
    )
    @settings(max_examples=100)
    def test_safe_data_preserved(self, safe_payload):
        """Property: Non-sensitive market data passes through unchanged.

        **Validates: Requirements 17.5**

        Sanitization only removes sensitive fields — all market data,
        prices, and technical indicators remain intact.
        """
        service = self._make_service()
        result = service.sanitize_payload(safe_payload)

        assert result == safe_payload, (
            f"Safe payload was modified during sanitization.\n"
            f"Input:  {safe_payload}\n"
            f"Output: {result}"
        )

    @given(
        sensitive_key=sensitive_keys_st,
        sensitive_val=sensitive_values_st,
        nesting_depth=st.integers(min_value=1, max_value=4),
    )
    @settings(max_examples=100)
    def test_sensitive_stripped_at_any_depth(self, sensitive_key, sensitive_val, nesting_depth):
        """Property: A sensitive key is stripped regardless of how deeply nested it is.

        **Validates: Requirements 17.5**

        Even if a sensitive field is buried N levels deep, sanitization removes it.
        """
        service = self._make_service()
        # Build a nested payload with the sensitive key at the specified depth
        payload = {sensitive_key: sensitive_val}
        for i in range(nesting_depth):
            payload = {f"level_{i}": payload}

        result = service.sanitize_payload(payload)

        # The sensitive key should not appear at any level
        output_keys = all_keys_recursive(result)
        assert sensitive_key.lower() not in output_keys, (
            f"Sensitive key '{sensitive_key}' survived sanitization at depth {nesting_depth}"
        )

    @given(
        sensitive_key=sensitive_keys_st,
        sensitive_val=sensitive_values_st,
    )
    @settings(max_examples=50)
    def test_sensitive_stripped_inside_list(self, sensitive_key, sensitive_val):
        """Property: Sensitive keys inside dicts within lists are also stripped.

        **Validates: Requirements 17.5**

        Lists containing dict elements get each dict element sanitized.
        """
        service = self._make_service()
        payload = {
            "items": [
                {"safe_field": "market_data", sensitive_key: sensitive_val},
                {sensitive_key: sensitive_val, "price": 100.0},
            ]
        }

        result = service.sanitize_payload(payload)

        # Check each dict in the list
        for item in result["items"]:
            if isinstance(item, dict):
                item_keys = {k.lower() for k in item.keys()}
                assert sensitive_key.lower() not in item_keys, (
                    f"Sensitive key '{sensitive_key}' leaked inside list item"
                )

    @given(
        num_sensitive=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    def test_multiple_sensitive_fields_all_stripped(self, num_sensitive):
        """Property: Multiple sensitive fields in one payload are all removed.

        **Validates: Requirements 17.5**

        Even when the payload contains many different sensitive keys,
        all of them are stripped simultaneously.
        """
        service = self._make_service()
        # Pick N sensitive keys
        sensitive_list = sorted(SENSITIVE_FIELDS)[:num_sensitive]

        payload = {"symbol": "NIFTY", "entry_price": 22500.0}
        for key in sensitive_list:
            payload[key] = f"secret_value_{key}"

        result = service.sanitize_payload(payload)

        output_keys = {k.lower() for k in result.keys()}
        for key in sensitive_list:
            assert key not in output_keys, (
                f"Sensitive key '{key}' was not stripped"
            )

        # Safe fields preserved
        assert result["symbol"] == "NIFTY"
        assert result["entry_price"] == 22500.0
