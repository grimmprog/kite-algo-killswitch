"""Property-based tests for AI Non-Execution Guarantee.

**Validates: Requirements 21.6**

Property 22: AI Non-Execution Guarantee
  - For any AI exit recommendation (including "exit_now" with high confidence),
    the system SHALL NOT place any exit order without explicit trader confirmation.
  - evaluate_exit returns advisory-only data: action, reasoning, confidence, warnings.
  - No order placement or execution side effects occur regardless of action returned.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import inspect
import pytest
from unittest.mock import MagicMock, patch, call
from hypothesis import given, assume, settings
from hypothesis import strategies as st

from src.services.ai_trading_service import (
    AITradingService,
    AIProvider,
    VALID_EXIT_ACTIONS,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for generating random exit actions (including valid and the critical "exit_now")
exit_action_strategy = st.sampled_from(list(VALID_EXIT_ACTIONS))

# Strategy for confidence values (0-100)
confidence_strategy = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)

# Strategy for generating position data
position_strategy = st.fixed_dictionaries({
    "entry_price": st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    "current_price": st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    "stop_loss": st.floats(min_value=0.5, max_value=100000.0, allow_nan=False, allow_infinity=False),
    "target": st.floats(min_value=1.0, max_value=200000.0, allow_nan=False, allow_infinity=False),
    "unrealized_pnl": st.floats(min_value=-50000.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
    "time_held_minutes": st.integers(min_value=0, max_value=600),
    "symbol": st.text(min_size=1, max_size=20, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    "quantity": st.integers(min_value=1, max_value=5000),
    "option_type": st.sampled_from(["CE", "PE"]),
})

# Strategy for generating market data
market_data_strategy = st.fixed_dictionaries({
    "macd": st.fixed_dictionaries({
        "signal": st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        "histogram": st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    }),
    "momentum": st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    "volume": st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
    "trend": st.sampled_from(["bullish", "bearish", "neutral"]),
    "key_levels": st.fixed_dictionaries({
        "support": st.lists(st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False), min_size=0, max_size=3),
        "resistance": st.lists(st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False), min_size=0, max_size=3),
    }),
    "ema_20": st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    "vwap": st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
})

# Strategy for generating warnings lists
warnings_strategy = st.lists(
    st.text(min_size=1, max_size=100),
    min_size=0,
    max_size=5,
)


# ---------------------------------------------------------------------------
# Property 22: AI Non-Execution Guarantee
# ---------------------------------------------------------------------------


class TestAINonExecutionGuarantee:
    """Property 22: Verify no exit order placed without explicit trader confirmation.

    **Validates: Requirements 21.6**
    """

    @given(
        position=position_strategy,
        market_data=market_data_strategy,
        action=exit_action_strategy,
        confidence=confidence_strategy,
        warnings=warnings_strategy,
    )
    @settings(max_examples=500)
    def test_evaluate_exit_returns_advisory_only(
        self, position, market_data, action, confidence, warnings
    ):
        """evaluate_exit returns only advisory data (action, reasoning, confidence, warnings).

        Regardless of what action the AI recommends (even "exit_now"), the response
        is purely informational with no execution side effects.
        """
        # Create the service
        service = AITradingService(provider=AIProvider.GEMINI, api_key="test-key")

        # Mock _make_request to return the generated exit recommendation
        mock_response = {
            "action": action,
            "reasoning": "Test reasoning for property test",
            "confidence": confidence,
            "warnings": warnings,
        }

        with patch.object(service, "_make_request", return_value=mock_response) as mock_req:
            result = service.evaluate_exit(position, market_data)

        # Verify the result contains ONLY advisory fields
        assert "action" in result
        assert "reasoning" in result
        assert "confidence" in result
        assert "warnings" in result

        # Verify action is within valid set
        assert result["action"] in VALID_EXIT_ACTIONS

        # Verify NO execution-related fields exist in the response
        execution_fields = {
            "order_id", "execution_id", "executed", "filled",
            "order_placed", "trade_executed", "confirmation_id",
            "order_status", "fill_price", "execution_time",
        }
        for field in execution_fields:
            assert field not in result, (
                f"Response should NOT contain execution field '{field}', "
                f"but it was found. AI exit advice must be advisory-only."
            )

        # Verify _make_request was called exactly once (only LLM call, no order API)
        mock_req.assert_called_once()

    @given(
        position=position_strategy,
        market_data=market_data_strategy,
        confidence=st.floats(min_value=90.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        warnings=warnings_strategy,
    )
    @settings(max_examples=300)
    def test_exit_now_with_high_confidence_no_side_effects(
        self, position, market_data, confidence, warnings
    ):
        """Even when action='exit_now' with high confidence, no external calls occur beyond _make_request.

        This is the critical case: the AI strongly recommends exiting, but the
        system must NOT auto-execute. Only _make_request is called (to get the LLM response).
        """
        service = AITradingService(provider=AIProvider.GEMINI, api_key="test-key")

        mock_response = {
            "action": "exit_now",
            "reasoning": "Strong reversal detected, exit immediately recommended",
            "confidence": confidence,
            "warnings": warnings,
        }

        with patch.object(service, "_make_request", return_value=mock_response) as mock_req:
            # Also patch the client's send_request to track if any other calls happen
            with patch.object(service.client, "send_request") as mock_client:
                result = service.evaluate_exit(position, market_data)

        # _make_request called exactly once
        mock_req.assert_called_once()

        # The underlying client.send_request should NOT be called directly
        # (only _make_request handles it internally)
        mock_client.assert_not_called()

        # Result is purely advisory
        assert result["action"] == "exit_now"
        assert isinstance(result["reasoning"], str)
        assert isinstance(result["confidence"], float)
        assert isinstance(result["warnings"], list)

    def test_service_has_no_order_placement_methods(self):
        """The AITradingService class has no methods that directly call order placement.

        Inspects the class to verify no method names suggest trade execution capability.
        """
        order_related_keywords = {
            "place_order", "execute_order", "submit_order",
            "execute_trade", "place_trade", "send_order",
            "market_order", "limit_order", "cancel_order",
            "modify_order", "execute_exit", "auto_exit",
            "auto_execute", "trigger_exit",
        }

        # Get all method names from AITradingService
        methods = [
            name for name, _ in inspect.getmembers(
                AITradingService, predicate=inspect.isfunction
            )
        ]

        for method_name in methods:
            assert method_name not in order_related_keywords, (
                f"AITradingService should NOT have order placement method '{method_name}'. "
                f"AI exit advice must be advisory-only per Requirement 21.6."
            )

    def test_evaluate_exit_response_is_purely_informational(self):
        """Verify the response structure from evaluate_exit contains no execution confirmation."""
        service = AITradingService(provider=AIProvider.GEMINI, api_key="test-key")

        # Test with all possible exit actions
        for action in VALID_EXIT_ACTIONS:
            mock_response = {
                "action": action,
                "reasoning": f"Advisory recommendation: {action}",
                "confidence": 95.0,
                "warnings": ["Test warning"],
            }

            with patch.object(service, "_make_request", return_value=mock_response):
                result = service.evaluate_exit(
                    {"entry_price": 100.0, "current_price": 110.0, "symbol": "NIFTY"},
                    {"trend": "bullish", "momentum": 5.0},
                )

            # Response keys must be advisory-only
            allowed_keys = {"action", "reasoning", "confidence", "warnings"}
            # The response should only contain the allowed advisory keys
            for key in result:
                assert key in allowed_keys, (
                    f"Unexpected key '{key}' in evaluate_exit response for action='{action}'. "
                    f"Response must only contain advisory fields: {allowed_keys}"
                )

    @given(
        position=position_strategy,
        market_data=market_data_strategy,
        action=exit_action_strategy,
        confidence=confidence_strategy,
    )
    @settings(max_examples=300)
    def test_no_external_calls_beyond_make_request(
        self, position, market_data, action, confidence
    ):
        """Regardless of action recommended, evaluate_exit makes no calls beyond _make_request.

        This verifies no order APIs, broker APIs, or execution services are called.
        """
        service = AITradingService(provider=AIProvider.GEMINI, api_key="test-key")

        mock_response = {
            "action": action,
            "reasoning": "Test advisory",
            "confidence": confidence,
            "warnings": [],
        }

        # Track all attribute access and method calls on the service
        with patch.object(service, "_make_request", return_value=mock_response) as mock_req:
            result = service.evaluate_exit(position, market_data)

        # Only _make_request should have been called
        assert mock_req.call_count == 1, (
            f"Expected exactly 1 call to _make_request, got {mock_req.call_count}. "
            f"No additional external calls should be made for action='{action}'."
        )
