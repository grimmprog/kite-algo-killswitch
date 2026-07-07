"""Tests for AITradingService — core functionality, rate limiting, and data safety.

Tests Requirements: 17.1, 17.2, 17.3, 17.4, 17.5
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
from unittest.mock import MagicMock, patch

import pytest

from src.services.ai_trading_service import (
    AIProvider,
    AIProviderClient,
    AIProviderError,
    AITradingService,
    ClaudeClient,
    GeminiClient,
    TokenBucketRateLimiter,
    create_provider_client,
    SENSITIVE_FIELDS,
)


# ---------------------------------------------------------------------------
# TokenBucketRateLimiter tests
# ---------------------------------------------------------------------------


class TestTokenBucketRateLimiter:
    """Tests for the token bucket rate limiter."""

    def test_initial_tokens_available(self):
        """Rate limiter starts with full bucket."""
        limiter = TokenBucketRateLimiter(max_tokens=30, refill_rate=0.5)
        assert limiter.available_tokens == 30.0

    def test_consume_decreases_tokens(self):
        """Each consume reduces available tokens by 1."""
        limiter = TokenBucketRateLimiter(max_tokens=30, refill_rate=0.5)
        assert limiter.consume() is True
        assert limiter.available_tokens < 30.0

    def test_consume_returns_false_when_empty(self):
        """Returns False when no tokens are available."""
        limiter = TokenBucketRateLimiter(max_tokens=3, refill_rate=0.5)
        # Consume all tokens
        for _ in range(3):
            assert limiter.consume() is True
        # Next consume should fail
        assert limiter.consume() is False

    def test_tokens_refill_over_time(self):
        """Tokens refill based on elapsed time and refill_rate."""
        limiter = TokenBucketRateLimiter(max_tokens=30, refill_rate=10.0)
        # Consume all tokens
        for _ in range(30):
            limiter.consume()
        # Simulate time passing (use internal manipulation for test speed)
        limiter.last_refill_time = time.monotonic() - 1.0  # 1 second ago
        # Should have ~10 tokens now (10.0 refill_rate × 1 second)
        assert limiter.available_tokens >= 9.5

    def test_tokens_do_not_exceed_max(self):
        """Refill never exceeds max_tokens."""
        limiter = TokenBucketRateLimiter(max_tokens=5, refill_rate=100.0)
        # Even with very high refill, stays at max
        limiter.last_refill_time = time.monotonic() - 10.0
        assert limiter.available_tokens == 5.0

    def test_30_requests_per_minute_capacity(self):
        """Bucket allows 30 requests before needing refill."""
        limiter = TokenBucketRateLimiter(max_tokens=30, refill_rate=0.5)
        consumed = 0
        for _ in range(35):
            if limiter.consume():
                consumed += 1
        assert consumed == 30


# ---------------------------------------------------------------------------
# Provider Factory tests
# ---------------------------------------------------------------------------


class TestProviderFactory:
    """Tests for the AI provider factory function."""

    def test_creates_gemini_client(self):
        """Factory returns GeminiClient for GEMINI provider."""
        client = create_provider_client(AIProvider.GEMINI, "test-key")
        assert isinstance(client, GeminiClient)
        assert client.api_key == "test-key"

    def test_creates_claude_client(self):
        """Factory returns ClaudeClient for CLAUDE provider."""
        client = create_provider_client(AIProvider.CLAUDE, "test-key")
        assert isinstance(client, ClaudeClient)
        assert client.api_key == "test-key"

    def test_raises_for_invalid_provider(self):
        """Factory raises ValueError for unsupported provider."""
        with pytest.raises(ValueError, match="Unsupported AI provider"):
            create_provider_client("unknown", "test-key")


# ---------------------------------------------------------------------------
# Data Sanitization tests
# ---------------------------------------------------------------------------


class TestDataSanitization:
    """Tests for payload sanitization before LLM submission."""

    @pytest.fixture
    def service(self):
        """Create an AITradingService instance for testing."""
        return AITradingService(provider=AIProvider.GEMINI, api_key="test-key")

    def test_strips_api_key(self, service):
        """Removes api_key from payload."""
        payload = {"symbol": "NIFTY", "api_key": "secret123", "price": 100.0}
        result = service.sanitize_payload(payload)
        assert "api_key" not in result
        assert result["symbol"] == "NIFTY"
        assert result["price"] == 100.0

    def test_strips_credentials(self, service):
        """Removes credential-related fields."""
        payload = {
            "symbol": "NIFTY",
            "access_token": "tok_123",
            "password": "pass",
            "credentials": {"user": "x"},
            "token": "abc",
            "secret": "shh",
        }
        result = service.sanitize_payload(payload)
        assert "access_token" not in result
        assert "password" not in result
        assert "credentials" not in result
        assert "token" not in result
        assert "secret" not in result
        assert result["symbol"] == "NIFTY"

    def test_strips_pii_fields(self, service):
        """Removes PII fields like email, phone, pan."""
        payload = {
            "signal_type": "trend_pullback",
            "email": "trader@example.com",
            "phone": "9876543210",
            "pan": "ABCDE1234F",
            "aadhaar": "1234-5678-9012",
            "name": "John Doe",
        }
        result = service.sanitize_payload(payload)
        assert "email" not in result
        assert "phone" not in result
        assert "pan" not in result
        assert "aadhaar" not in result
        assert "name" not in result
        assert result["signal_type"] == "trend_pullback"

    def test_strips_financial_pii(self, service):
        """Removes financial PII like balances and account numbers."""
        payload = {
            "entry_price": 250.0,
            "balance": 500000.0,
            "account_balance": 500000.0,
            "bank_account": "1234567890",
            "client_id": "AB1234",
        }
        result = service.sanitize_payload(payload)
        assert "balance" not in result
        assert "account_balance" not in result
        assert "bank_account" not in result
        assert "client_id" not in result
        assert result["entry_price"] == 250.0

    def test_recursive_sanitization(self, service):
        """Sanitizes nested dictionaries recursively."""
        payload = {
            "signal": {
                "symbol": "NIFTY",
                "api_key": "hidden",
                "nested": {"password": "pw", "price": 100.0},
            },
            "market_data": {"vwap": 22500.0, "token": "session_tok"},
        }
        result = service.sanitize_payload(payload)
        assert "api_key" not in result["signal"]
        assert "password" not in result["signal"]["nested"]
        assert result["signal"]["nested"]["price"] == 100.0
        assert "token" not in result["market_data"]
        assert result["market_data"]["vwap"] == 22500.0

    def test_sanitizes_dicts_in_lists(self, service):
        """Sanitizes dictionaries within list values."""
        payload = {
            "candles": [
                {"open": 100, "close": 105, "api_key": "x"},
                {"open": 105, "close": 110, "password": "y"},
            ]
        }
        result = service.sanitize_payload(payload)
        assert "api_key" not in result["candles"][0]
        assert "password" not in result["candles"][1]
        assert result["candles"][0]["open"] == 100
        assert result["candles"][1]["close"] == 110

    def test_preserves_market_data(self, service):
        """Market data, prices, and indicators pass through unchanged."""
        payload = {
            "symbol": "BANKNIFTY",
            "entry_price": 48500.0,
            "stop_loss": 48200.0,
            "target": 49000.0,
            "ema_20": 48400.0,
            "vwap": 48450.0,
            "macd": {"signal": 12.5, "histogram": 3.2},
            "volume": 1500000,
            "trend_direction": "bullish",
        }
        result = service.sanitize_payload(payload)
        assert result == payload

    def test_case_insensitive_matching(self, service):
        """Sensitive field matching is case-insensitive."""
        payload = {"Symbol": "NIFTY", "API_KEY": "secret", "Password": "pass"}
        result = service.sanitize_payload(payload)
        # API_KEY and Password are stripped (lowered to match)
        assert "API_KEY" not in result
        assert "Password" not in result
        assert result["Symbol"] == "NIFTY"

    def test_empty_payload(self, service):
        """Empty payload returns empty dict."""
        assert service.sanitize_payload({}) == {}

    def test_non_dict_input(self, service):
        """Non-dict input is returned as-is."""
        assert service.sanitize_payload("hello") == "hello"
        assert service.sanitize_payload(42) == 42


# ---------------------------------------------------------------------------
# Graceful Degradation tests
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Tests for graceful degradation on AI API errors."""

    @pytest.fixture
    def service(self):
        """Create an AITradingService with a mocked provider client."""
        svc = AITradingService(provider=AIProvider.GEMINI, api_key="test-key")
        svc.client = MagicMock()
        return svc

    def test_returns_unavailable_on_provider_error(self, service):
        """Returns graceful response on AIProviderError."""
        service.client.send_request.side_effect = AIProviderError("API down")
        result = service._make_request("test prompt", {"data": "test"})
        assert result["error"] is True
        assert result["message"] == "AI analysis unavailable"
        assert result["available"] is False

    def test_returns_unavailable_on_timeout(self, service):
        """Returns graceful response on TimeoutError."""
        service.client.send_request.side_effect = TimeoutError("Request timed out")
        result = service._make_request("test prompt", {"data": "test"})
        assert result["error"] is True
        assert result["message"] == "AI analysis unavailable"
        assert result["available"] is False

    def test_returns_unavailable_on_unexpected_error(self, service):
        """Returns graceful response on unexpected exceptions."""
        service.client.send_request.side_effect = RuntimeError("Unexpected")
        result = service._make_request("test prompt", {"data": "test"})
        assert result["error"] is True
        assert result["message"] == "AI analysis unavailable"
        assert result["available"] is False

    def test_returns_rate_limit_message_when_exhausted(self, service):
        """Returns rate limit error when tokens are exhausted."""
        # Exhaust the rate limiter
        for _ in range(30):
            service.rate_limiter.consume()
        result = service._make_request("test prompt", {"data": "test"})
        assert result["error"] is True
        assert "rate limit" in result["message"].lower()
        assert result["available"] is False
        # Verify the provider was never called
        service.client.send_request.assert_not_called()

    def test_successful_request_passes_through(self, service):
        """Successful responses are returned as-is."""
        expected = {"quality_rating": "Strong Setup", "warnings": []}
        service.client.send_request.return_value = expected
        result = service._make_request("test prompt", {"symbol": "NIFTY"})
        assert result == expected

    def test_sanitizes_before_sending(self, service):
        """Context is sanitized before being sent to provider."""
        expected = {"response": "ok"}
        service.client.send_request.return_value = expected

        context = {"symbol": "NIFTY", "api_key": "SECRET", "price": 100.0}
        service._make_request("test prompt", context)

        # Check the context passed to send_request has no api_key
        call_args = service.client.send_request.call_args
        sent_context = call_args[1]["context"] if "context" in call_args[1] else call_args[0][1]
        assert "api_key" not in sent_context


# ---------------------------------------------------------------------------
# AITradingService initialization tests
# ---------------------------------------------------------------------------


class TestAITradingServiceInit:
    """Tests for AITradingService initialization."""

    def test_initializes_with_gemini(self):
        """Creates service with Gemini provider."""
        svc = AITradingService(provider=AIProvider.GEMINI, api_key="gemini-key")
        assert svc.provider == AIProvider.GEMINI
        assert svc.api_key == "gemini-key"
        assert isinstance(svc.client, GeminiClient)
        assert isinstance(svc.rate_limiter, TokenBucketRateLimiter)

    def test_initializes_with_claude(self):
        """Creates service with Claude provider."""
        svc = AITradingService(provider=AIProvider.CLAUDE, api_key="claude-key")
        assert svc.provider == AIProvider.CLAUDE
        assert isinstance(svc.client, ClaudeClient)

    def test_rate_limiter_configured_correctly(self):
        """Rate limiter uses 30 max tokens and 0.5 refill rate."""
        svc = AITradingService(provider=AIProvider.GEMINI, api_key="key")
        assert svc.rate_limiter.max_tokens == 30
        assert svc.rate_limiter.refill_rate == 0.5


# ---------------------------------------------------------------------------
# Service method delegation tests
# ---------------------------------------------------------------------------


class TestServiceMethods:
    """Tests that service methods properly delegate to _make_request."""

    @pytest.fixture
    def service(self):
        """Create a service with mocked internal request method."""
        svc = AITradingService(provider=AIProvider.GEMINI, api_key="test-key")
        svc._make_request = MagicMock(return_value={"response": "ok"})
        return svc

    def test_analyze_signal_calls_make_request(self, service):
        """analyze_signal delegates to _make_request with 5s timeout."""
        result = service.analyze_signal({"symbol": "NIFTY"})
        service._make_request.assert_called_once()
        call_kwargs = service._make_request.call_args
        assert call_kwargs[1]["timeout"] == 5.0 or call_kwargs[0][2] == 5.0

    def test_suggest_entry_combines_context(self, service):
        """suggest_entry combines signal and market data in context."""
        service.suggest_entry({"symbol": "NIFTY"}, {"vwap": 22500})
        service._make_request.assert_called_once()

    def test_analyze_consolidation_delegates(self, service):
        """analyze_consolidation delegates to _make_request."""
        service.analyze_consolidation({"range_high": 100}, {"trend": "bullish"})
        service._make_request.assert_called_once()

    def test_evaluate_exit_delegates(self, service):
        """evaluate_exit delegates to _make_request."""
        service.evaluate_exit({"position_id": 1}, {"price": 250})
        service._make_request.assert_called_once()

    def test_generate_narrative_delegates(self, service):
        """generate_narrative delegates to _make_request."""
        service.generate_narrative("morning_brief", {"indices": {}})
        service._make_request.assert_called_once()

    def test_review_trade_delegates(self, service):
        """review_trade delegates to _make_request."""
        service.review_trade({"trade_id": 1}, {"history": []})
        service._make_request.assert_called_once()

    def test_detect_risk_anomalies_delegates(self, service):
        """detect_risk_anomalies delegates to _make_request."""
        service.detect_risk_anomalies({"losses": 3}, {"volatility": "high"})
        service._make_request.assert_called_once()


class TestReviewTradeIntegration:
    """Tests for review_trade method — prompt quality, format_trade_review parsing."""

    @pytest.fixture
    def service(self):
        """Create a service with mocked _make_request that returns valid review data."""
        svc = AITradingService(provider=AIProvider.GEMINI, api_key="test-key")
        return svc

    def test_review_trade_uses_format_trade_review(self, service):
        """review_trade parses LLM response through format_trade_review."""
        mock_response = {
            "grade": "B",
            "entry_feedback": "Entry was 2 candles late",
            "exit_feedback": "Exit timing was good",
            "sizing_feedback": "Position size appropriate",
            "risk_feedback": "Risk well managed",
            "optimal_comparison": "Optimal entry at 86.70 would have yielded +2340",
            "patterns_identified": ["exits too early on winners"],
        }
        service._make_request = MagicMock(return_value=mock_response)

        result = service.review_trade(
            {"symbol": "NIFTY", "entry_price": 87.0, "exit_price": 90.0},
            {"candles": []},
        )

        assert result["grade"] == "B"
        assert result["entry_feedback"] == "Entry was 2 candles late"
        assert result["exit_feedback"] == "Exit timing was good"
        assert result["sizing_feedback"] == "Position size appropriate"
        assert result["risk_feedback"] == "Risk well managed"
        assert result["optimal_comparison"] == "Optimal entry at 86.70 would have yielded +2340"
        assert result["patterns_identified"] == ["exits too early on winners"]

    def test_review_trade_invalid_grade_defaults_to_c(self, service):
        """review_trade defaults grade to C when LLM returns invalid grade."""
        mock_response = {
            "grade": "X",  # Invalid grade
            "entry_feedback": "Good entry",
            "exit_feedback": "Good exit",
            "sizing_feedback": "Ok",
            "risk_feedback": "Ok",
            "optimal_comparison": "Close to optimal",
            "patterns_identified": [],
        }
        service._make_request = MagicMock(return_value=mock_response)

        result = service.review_trade({"symbol": "NIFTY"}, {})
        assert result["grade"] == "C"

    def test_review_trade_missing_fields_get_defaults(self, service):
        """review_trade provides defaults for missing feedback fields."""
        mock_response = {"grade": "A"}  # Minimal response
        service._make_request = MagicMock(return_value=mock_response)

        result = service.review_trade({"symbol": "NIFTY"}, {})
        assert result["grade"] == "A"
        assert result["entry_feedback"] == "No feedback available"
        assert result["exit_feedback"] == "No feedback available"
        assert result["sizing_feedback"] == "No feedback available"
        assert result["risk_feedback"] == "No feedback available"
        assert result["optimal_comparison"] == "No comparison available"
        assert result["patterns_identified"] == []

    def test_review_trade_error_response_returned_as_is(self, service):
        """review_trade returns error response without parsing on failure."""
        error_response = {
            "error": True,
            "message": "AI rate limit exceeded. Please try again shortly.",
            "available": False,
        }
        service._make_request = MagicMock(return_value=error_response)

        result = service.review_trade({"symbol": "NIFTY"}, {})
        assert result["error"] is True
        assert result["message"] == "AI rate limit exceeded. Please try again shortly."

    def test_review_trade_prompt_contains_grading_criteria(self, service):
        """review_trade prompt includes grading criteria and analysis requirements."""
        service._make_request = MagicMock(return_value={"grade": "C"})

        service.review_trade(
            {"symbol": "NIFTY", "entry_price": 100, "exit_price": 110},
            {"candles": []},
        )

        call_args = service._make_request.call_args
        prompt = call_args[1]["prompt"] if "prompt" in (call_args[1] or {}) else call_args[0][0]
        assert "A:" in prompt or "A: Excellent" in prompt
        assert "F:" in prompt or "F: Poor" in prompt
        assert "entry_feedback" in prompt.lower() or "Entry Timing" in prompt
        assert "exit_feedback" in prompt.lower() or "Exit Timing" in prompt
        assert "sizing_feedback" in prompt.lower() or "Position Sizing" in prompt
        assert "risk_feedback" in prompt.lower() or "Risk Management" in prompt
        assert "optimal_comparison" in prompt.lower() or "Optimal Comparison" in prompt
        assert "patterns_identified" in prompt.lower() or "Pattern Identification" in prompt


class TestGenerateNarrativeIntegration:
    """Tests for generate_narrative — session types, format_narrative parsing."""

    @pytest.fixture
    def service(self):
        """Create a service instance."""
        svc = AITradingService(provider=AIProvider.GEMINI, api_key="test-key")
        return svc

    def test_generate_narrative_valid_session_types(self, service):
        """generate_narrative accepts all four valid session types."""
        mock_response = {
            "session_type": "morning_brief",
            "key_points": ["Market opened flat"],
            "bias": "neutral",
            "expected_range": {"low": 22000, "high": 22200},
            "key_levels": {"support": [22000], "resistance": [22200]},
        }
        service._make_request = MagicMock(return_value=mock_response)

        for session in ["morning_brief", "mid_morning", "lunch", "afternoon"]:
            mock_response["session_type"] = session
            result = service.generate_narrative(session, {"indices": {}})
            assert result["session_type"] == session

    def test_generate_narrative_invalid_session_defaults(self, service):
        """generate_narrative defaults invalid session_type to morning_brief."""
        mock_response = {
            "session_type": "invalid_session",
            "key_points": ["Point 1"],
            "bias": "neutral",
            "expected_range": {"low": 0, "high": 0},
            "key_levels": {"support": [], "resistance": []},
        }
        service._make_request = MagicMock(return_value=mock_response)

        result = service.generate_narrative("invalid_session", {})
        # format_narrative defaults invalid session_type to "morning_brief"
        assert result["session_type"] == "morning_brief"

    def test_generate_narrative_truncates_key_points_to_5(self, service):
        """generate_narrative enforces max 5 key points."""
        mock_response = {
            "session_type": "morning_brief",
            "key_points": ["P1", "P2", "P3", "P4", "P5", "P6", "P7"],
            "bias": "bullish",
            "expected_range": {"low": 22000, "high": 22200},
            "key_levels": {"support": [22000], "resistance": [22200]},
        }
        service._make_request = MagicMock(return_value=mock_response)

        result = service.generate_narrative("morning_brief", {})
        assert len(result["key_points"]) == 5

    def test_generate_narrative_error_response_returned_as_is(self, service):
        """generate_narrative returns error response on failure."""
        error_response = {
            "error": True,
            "message": "AI analysis unavailable",
            "available": False,
        }
        service._make_request = MagicMock(return_value=error_response)

        result = service.generate_narrative("morning_brief", {})
        assert result["error"] is True
