"""AI Trading Service — LLM-powered trading analysis with rate limiting and safety.

Integrates with configurable LLM providers (Gemini/Claude) to provide
signal analysis, entry suggestions, exit recommendations, market narrative,
trade review, and risk anomaly detection.

Implements Requirements: 17.1, 17.2, 17.3, 17.4, 17.5
"""

import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums and Models
# ---------------------------------------------------------------------------


class AIProvider(str, Enum):
    """Supported AI/LLM provider backends."""

    GEMINI = "gemini"
    CLAUDE = "claude"


class AIQualityRating(str, Enum):
    """Signal quality ratings from AI analysis."""

    STRONG = "Strong Setup"
    ACCEPTABLE = "Acceptable Setup"
    WEAK = "Weak Setup"
    AVOID = "Avoid — High Risk"


class AISignalAnalysis(BaseModel):
    """Result of AI signal quality analysis."""

    quality_rating: AIQualityRating
    warnings: List[str]
    explanation: str  # 2-3 sentences
    suggested_entry: Optional[float] = None
    suggested_sl: Optional[str] = None
    risk_reward_default: Optional[float] = None
    risk_reward_ai: Optional[float] = None
    timing_recommendation: Optional[str] = None


class AIConsolidationAnalysis(BaseModel):
    """Result of AI consolidation breakout analysis."""

    breakout_probability: float  # 0-100
    predicted_direction: str  # "up" or "down"
    expected_move_pct: float
    false_breakout_risk: bool
    false_breakout_reasons: List[str]
    assessment: Optional[str] = None  # real-time breakout assessment


class AIExitRecommendation(BaseModel):
    """AI recommendation for position exit strategy."""

    action: str  # "hold", "tighten_stop", "book_partial", "exit_now"
    reasoning: str  # 1-2 sentences
    confidence: float  # 0-100
    warnings: List[str]


class AIMarketNarrative(BaseModel):
    """AI-generated market context and commentary."""

    session_type: str  # "morning_brief", "mid_morning", "lunch", "afternoon"
    key_points: List[str]  # max 5
    bias: str  # "bullish", "bearish", "neutral"
    expected_range: Dict[str, float]  # {"low": float, "high": float}
    key_levels: Dict[str, List[float]]  # {"support": [...], "resistance": [...]}
    detailed_analysis: Optional[str] = None


class AITradeReview(BaseModel):
    """AI review of a completed trade."""

    grade: str  # A/B/C/D/F
    entry_feedback: str
    exit_feedback: str
    sizing_feedback: str
    risk_feedback: str
    optimal_comparison: str
    patterns_identified: List[str]


class AIRiskWarning(BaseModel):
    """AI-generated risk warning or behavioral alert."""

    severity: str  # "info", "warning", "critical"
    message: str
    category: str  # "market_condition", "behavioral", "rule_violation"
    requires_acknowledgment: bool


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Evaluation cycle interval for open positions (seconds) — Requirement 21.1
EXIT_EVALUATION_INTERVAL: int = 30

# Valid exit recommendation actions
VALID_EXIT_ACTIONS = frozenset({"hold", "tighten_stop", "book_partial", "exit_now"})

# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------

# Sensitive fields that must be stripped from payloads before sending to LLM
SENSITIVE_FIELDS = frozenset(
    {
        "api_key",
        "api_secret",
        "access_token",
        "refresh_token",
        "password",
        "token",
        "credentials",
        "secret",
        "session_token",
        "auth_token",
        "broker_key",
        "broker_secret",
        "kite_api_key",
        "kite_access_token",
        # PII fields
        "email",
        "phone",
        "phone_number",
        "mobile",
        "address",
        "pan",
        "pan_number",
        "aadhaar",
        "aadhaar_number",
        "bank_account",
        "account_number",
        "ifsc",
        "name",
        "full_name",
        "first_name",
        "last_name",
        "date_of_birth",
        "dob",
        # Financial PII
        "account_balance",
        "balance",
        "available_balance",
        "net_worth",
        "demat_id",
        "client_id",
        "user_id",
    }
)


class TokenBucketRateLimiter:
    """Token bucket rate limiter for AI API calls.

    Implements a token bucket algorithm where:
    - max_tokens controls the burst capacity (30 by default)
    - refill_rate controls how fast tokens are added (0.5/sec = 30/min)

    This ensures at most 30 requests per 60-second rolling window while
    allowing short bursts when tokens are available.
    """

    def __init__(self, max_tokens: int = 30, refill_rate: float = 0.5) -> None:
        """Initialize the token bucket rate limiter.

        Args:
            max_tokens: Maximum tokens in the bucket (burst capacity).
            refill_rate: Rate at which tokens refill (tokens per second).
                         Default 0.5 = 30 tokens per minute.
        """
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.tokens = float(max_tokens)
        self.last_refill_time = time.monotonic()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self.last_refill_time
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.max_tokens, self.tokens + tokens_to_add)
        self.last_refill_time = now

    def consume(self) -> bool:
        """Attempt to consume one token.

        Returns:
            True if a token was consumed (request allowed),
            False if the bucket is empty (request rejected).
        """
        self._refill()
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

    @property
    def available_tokens(self) -> float:
        """Get the current number of available tokens (after refill)."""
        self._refill()
        return self.tokens


# ---------------------------------------------------------------------------
# Provider Factory
# ---------------------------------------------------------------------------


class AIProviderClient:
    """Base AI provider client interface.

    Concrete implementations (Gemini, Claude) extend this to call their
    respective APIs. This base class provides the interface contract.
    """

    def __init__(self, api_key: str) -> None:
        """Initialize provider client with API key.

        Args:
            api_key: The API key for the provider.
        """
        self.api_key = api_key

    def send_request(
        self, prompt: str, context: Dict[str, Any], timeout: float = 5.0
    ) -> Dict[str, Any]:
        """Send a request to the LLM provider.

        Args:
            prompt: The instruction/query for the LLM.
            context: Sanitized context data (market data, indicators).
            timeout: Request timeout in seconds (default 5s).

        Returns:
            Dictionary with the LLM response.

        Raises:
            AIProviderError: On API errors or timeouts.
        """
        raise NotImplementedError("Subclasses must implement send_request")


class GeminiClient(AIProviderClient):
    """Google Gemini API client using REST API."""

    GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

    def send_request(
        self, prompt: str, context: Dict[str, Any], timeout: float = 5.0
    ) -> Dict[str, Any]:
        """Send request to Google Gemini API.

        Args:
            prompt: The instruction/query for the LLM.
            context: Sanitized context data.
            timeout: Request timeout in seconds.

        Returns:
            Dictionary with the parsed Gemini response.

        Raises:
            AIProviderError: On API errors or timeouts.
        """
        import json
        import requests as http_requests

        url = f"{self.GEMINI_API_URL}?key={self.api_key}"

        # Build the combined prompt with context
        full_prompt = f"{prompt}\n\nContext data:\n{json.dumps(context, indent=2, default=str)}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": full_prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 1024,
                "responseMimeType": "application/json",
            },
        }

        try:
            resp = http_requests.post(
                url,
                json=payload,
                timeout=timeout,
                headers={"Content-Type": "application/json"},
            )
        except http_requests.exceptions.Timeout:
            raise TimeoutError(f"Gemini API timed out after {timeout}s")
        except http_requests.exceptions.RequestException as e:
            raise AIProviderError(f"Gemini API request failed: {e}")

        if resp.status_code != 200:
            raise AIProviderError(
                f"Gemini API returned {resp.status_code}: {resp.text[:300]}"
            )

        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            raise AIProviderError("Failed to parse Gemini API response as JSON")

        # Extract text content from Gemini response structure
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                raise AIProviderError("Gemini returned no candidates")

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                raise AIProviderError("Gemini returned no content parts")

            text = parts[0].get("text", "")
        except (IndexError, KeyError, TypeError) as e:
            raise AIProviderError(f"Unexpected Gemini response structure: {e}")

        # Parse the response text as JSON
        try:
            # Strip markdown code fences if present
            cleaned = text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            result = json.loads(cleaned)
            return result if isinstance(result, dict) else {"data": result}
        except (json.JSONDecodeError, ValueError):
            # If not valid JSON, return as text in a dict
            return {"analysis": text, "raw_response": True}


class ClaudeClient(AIProviderClient):
    """Anthropic Claude API client."""

    CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"

    def send_request(
        self, prompt: str, context: Dict[str, Any], timeout: float = 5.0
    ) -> Dict[str, Any]:
        """Send request to Anthropic Claude API.

        Args:
            prompt: The instruction/query for the LLM.
            context: Sanitized context data.
            timeout: Request timeout in seconds.

        Returns:
            Dictionary with the parsed Claude response.

        Raises:
            AIProviderError: On API errors or timeouts.
        """
        import json
        import requests as http_requests

        full_prompt = f"{prompt}\n\nContext data:\n{json.dumps(context, indent=2, default=str)}"

        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "messages": [
                {"role": "user", "content": full_prompt}
            ],
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        try:
            resp = http_requests.post(
                self.CLAUDE_API_URL,
                json=payload,
                timeout=timeout,
                headers=headers,
            )
        except http_requests.exceptions.Timeout:
            raise TimeoutError(f"Claude API timed out after {timeout}s")
        except http_requests.exceptions.RequestException as e:
            raise AIProviderError(f"Claude API request failed: {e}")

        if resp.status_code != 200:
            raise AIProviderError(
                f"Claude API returned {resp.status_code}: {resp.text[:300]}"
            )

        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            raise AIProviderError("Failed to parse Claude API response as JSON")

        # Extract text from Claude response
        try:
            content_blocks = data.get("content", [])
            if not content_blocks:
                raise AIProviderError("Claude returned no content")

            text = content_blocks[0].get("text", "")
        except (IndexError, KeyError, TypeError) as e:
            raise AIProviderError(f"Unexpected Claude response structure: {e}")

        # Parse the response text as JSON
        try:
            cleaned = text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            result = json.loads(cleaned)
            return result if isinstance(result, dict) else {"data": result}
        except (json.JSONDecodeError, ValueError):
            return {"analysis": text, "raw_response": True}


class AIProviderError(Exception):
    """Raised when an AI provider API call fails."""

    pass


def create_provider_client(provider: AIProvider, api_key: str) -> AIProviderClient:
    """Factory function to create the appropriate AI provider client.

    Args:
        provider: The AI provider enum value (GEMINI or CLAUDE).
        api_key: The API key for authentication with the provider.

    Returns:
        An AIProviderClient instance for the specified provider.

    Raises:
        ValueError: If an unsupported provider is specified.
    """
    if provider == AIProvider.GEMINI:
        return GeminiClient(api_key)
    elif provider == AIProvider.CLAUDE:
        return ClaudeClient(api_key)
    else:
        raise ValueError(f"Unsupported AI provider: {provider}")


# ---------------------------------------------------------------------------
# AI Trading Service
# ---------------------------------------------------------------------------


VALID_SESSION_TYPES = ["morning_brief", "mid_morning", "lunch", "afternoon"]
VALID_GRADES = ["A", "B", "C", "D", "F"]
VALID_BIASES = ["bullish", "bearish", "neutral"]


def format_narrative(raw_response: dict) -> AIMarketNarrative:
    """Parse LLM response into AIMarketNarrative, enforcing constraints.

    - Enforces max 5 key points (truncates if more)
    - Validates bias is one of bullish/bearish/neutral (defaults to "neutral")
    - Provides defaults for missing fields

    Args:
        raw_response: Dictionary from LLM response.

    Returns:
        AIMarketNarrative with validated/constrained fields.
    """
    # Extract and enforce max 5 key points
    key_points = raw_response.get("key_points", [])
    if not isinstance(key_points, list):
        key_points = []
    key_points = key_points[:5]

    # Validate bias
    bias = raw_response.get("bias", "neutral")
    if bias not in VALID_BIASES:
        bias = "neutral"

    # Extract session_type with default
    session_type = raw_response.get("session_type", "morning_brief")
    if session_type not in VALID_SESSION_TYPES:
        session_type = "morning_brief"

    # Extract expected_range with defaults
    expected_range = raw_response.get("expected_range", {})
    if not isinstance(expected_range, dict):
        expected_range = {}
    expected_range.setdefault("low", 0.0)
    expected_range.setdefault("high", 0.0)

    # Extract key_levels with defaults
    key_levels = raw_response.get("key_levels", {})
    if not isinstance(key_levels, dict):
        key_levels = {}
    key_levels.setdefault("support", [])
    key_levels.setdefault("resistance", [])

    return AIMarketNarrative(
        session_type=session_type,
        key_points=key_points,
        bias=bias,
        expected_range=expected_range,
        key_levels=key_levels,
        detailed_analysis=raw_response.get("detailed_analysis"),
    )


def format_trade_review(raw_response: dict) -> AITradeReview:
    """Parse LLM response into AITradeReview, enforcing constraints.

    - Validates grade is one of A/B/C/D/F (defaults to "C")
    - Provides defaults for missing feedback fields

    Args:
        raw_response: Dictionary from LLM response.

    Returns:
        AITradeReview with validated fields and sensible defaults.
    """
    # Validate grade
    grade = raw_response.get("grade", "C")
    if grade not in VALID_GRADES:
        grade = "C"

    # Extract patterns_identified
    patterns = raw_response.get("patterns_identified", [])
    if not isinstance(patterns, list):
        patterns = []

    return AITradeReview(
        grade=grade,
        entry_feedback=raw_response.get("entry_feedback", "No feedback available"),
        exit_feedback=raw_response.get("exit_feedback", "No feedback available"),
        sizing_feedback=raw_response.get("sizing_feedback", "No feedback available"),
        risk_feedback=raw_response.get("risk_feedback", "No feedback available"),
        optimal_comparison=raw_response.get(
            "optimal_comparison", "No comparison available"
        ),
        patterns_identified=patterns,
    )


class AITradingService:
    """Orchestrates AI analysis across all trading features.

    Provides signal quality analysis, entry suggestions, consolidation
    analysis, exit recommendations, market narrative, trade review,
    and risk anomaly detection via configurable LLM providers.

    Features:
    - Token bucket rate limiting (30 req/min)
    - Data sanitization (strips credentials/PII before sending to LLM)
    - Graceful degradation (returns "AI unavailable" on errors)
    - Configurable provider (Gemini/Claude) via factory pattern
    """

    # Default timeout for AI API requests (seconds)
    DEFAULT_TIMEOUT: float = 10.0

    def __init__(self, provider: AIProvider, api_key: str) -> None:
        """Initialize AITradingService.

        Args:
            provider: The AI provider to use (GEMINI or CLAUDE).
            api_key: The API key for the configured provider.
        """
        self.provider = provider
        self.api_key = api_key
        self.rate_limiter = TokenBucketRateLimiter(max_tokens=30, refill_rate=0.5)
        self.client = create_provider_client(provider, api_key)

    def sanitize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive fields from payload before sending to LLM.

        Recursively strips credentials, PII, and other sensitive data
        from the payload dictionary. Only market data, price levels,
        and technical indicators should remain.

        Args:
            payload: The raw data dictionary to sanitize.

        Returns:
            A new dictionary with all sensitive fields removed.
        """
        if not isinstance(payload, dict):
            return payload

        sanitized = {}
        for key, value in payload.items():
            # Skip sensitive fields (case-insensitive match)
            if key.lower() in SENSITIVE_FIELDS:
                continue

            # Recursively sanitize nested dictionaries
            if isinstance(value, dict):
                sanitized[key] = self.sanitize_payload(value)
            # Sanitize dictionaries within lists
            elif isinstance(value, list):
                sanitized[key] = [
                    self.sanitize_payload(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                sanitized[key] = value

        return sanitized

    def _make_request(
        self, prompt: str, context: Dict[str, Any], timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """Make a rate-limited, sanitized request to the AI provider.

        This is the base request method that:
        1. Checks the rate limiter before proceeding
        2. Sanitizes the context payload to remove credentials/PII
        3. Calls the provider client with timeout
        4. Handles errors gracefully (returns degraded response)

        Args:
            prompt: The instruction/query for the LLM.
            context: Raw context data (will be sanitized before sending).
            timeout: Request timeout in seconds (defaults to DEFAULT_TIMEOUT).

        Returns:
            Dictionary with the AI response, or a graceful degradation
            response if the service is unavailable.
        """
        effective_timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT

        # Check rate limit
        if not self.rate_limiter.consume():
            logger.warning("AI rate limit exceeded for provider %s", self.provider)
            return {
                "error": True,
                "message": "AI rate limit exceeded. Please try again shortly.",
                "available": False,
            }

        # Sanitize the payload — never send credentials or PII to LLM
        sanitized_context = self.sanitize_payload(context)

        # Make the request with error handling and graceful degradation
        try:
            response = self.client.send_request(
                prompt=prompt,
                context=sanitized_context,
                timeout=effective_timeout,
            )
            return response
        except AIProviderError as e:
            logger.error(
                "AI provider error (%s): %s",
                self.provider,
                str(e),
            )
            return {
                "error": True,
                "message": f"AI analysis unavailable: {str(e)[:100]}",
                "available": False,
            }
        except TimeoutError:
            logger.warning(
                "AI request timed out after %.1fs (%s)",
                effective_timeout,
                self.provider,
            )
            return {
                "error": True,
                "message": f"AI analysis timed out after {effective_timeout}s",
                "available": False,
            }
        except Exception as e:
            # Catch-all for unexpected errors — never block trading
            logger.error(
                "Unexpected AI service error (%s): %s",
                self.provider,
                str(e),
                exc_info=True,
            )
            return {
                "error": True,
                "message": f"AI analysis unavailable: {type(e).__name__}: {str(e)[:100]}",
                "available": False,
            }

    @staticmethod
    def calculate_risk_reward(entry: float, stop_loss: float, target: float) -> float:
        """Calculate the risk:reward ratio for a trade.

        R:R = abs(target - entry) / abs(entry - stop_loss)

        Args:
            entry: Entry price.
            stop_loss: Stop-loss price.
            target: Target price.

        Returns:
            The risk-reward ratio as a float.  Returns 0.0 if entry == stop_loss
            (division by zero scenario).
        """
        risk = abs(entry - stop_loss)
        if risk == 0:
            return 0.0
        reward = abs(target - entry)
        return reward / risk

    def analyze_signal(self, signal_context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze signal quality with LLM. Must complete within 5 seconds.

        Sends the signal context (symbol, timeframe, indicator values, price
        action pattern, volume profile, and recent candle data) to the AI API
        for quality evaluation.

        The prompt instructs the LLM to return structured JSON with:
        - quality_rating: one of "Strong Setup", "Acceptable Setup",
          "Weak Setup", "Avoid — High Risk"
        - warnings: list of specific warning strings
        - explanation: 2-3 sentence natural language explanation

        Args:
            signal_context: Dictionary with signal data including:
                - symbol: Trading symbol (e.g., "NIFTY")
                - timeframe: Candle timeframe (e.g., "5min")
                - indicators: Dict with EMA, VWAP, MACD, RSI values
                - price_action_pattern: Detected pattern name
                - volume_profile: Volume analysis data
                - recent_candles: List of recent OHLCV candle dicts

        Returns:
            AISignalAnalysis data as dict with quality_rating, warnings,
            explanation fields, or degraded response on failure.

        Implements Requirements: 18.1, 18.2, 18.3, 18.4, 18.6
        """
        prompt = (
            "You are a professional trading signal analyst. Analyze the following "
            "trading signal and return a JSON response with exactly these fields:\n"
            "1. \"quality_rating\": one of \"Strong Setup\", \"Acceptable Setup\", "
            "\"Weak Setup\", or \"Avoid — High Risk\"\n"
            "2. \"warnings\": a list of specific warning strings. Consider these "
            "potential warnings:\n"
            "   - \"Entering against broader trend\"\n"
            "   - \"Low volume — breakout may fail\"\n"
            "   - \"Near major resistance — limited upside\"\n"
            "   - \"Expiry day risk — theta decay accelerating\"\n"
            "   - \"Extended move — mean reversion likely\"\n"
            "   - \"News event imminent — elevated volatility expected\"\n"
            "3. \"explanation\": 2-3 sentences describing why the setup is strong "
            "or weak based on price context, trend structure, and market conditions.\n\n"
            "Evaluate the signal based on:\n"
            "- Symbol and timeframe context\n"
            "- Indicator values (EMA, VWAP, MACD, RSI)\n"
            "- Price action pattern quality\n"
            "- Volume profile (confirmation or divergence)\n"
            "- Recent candle structure and momentum\n\n"
            "Return ONLY valid JSON, no markdown formatting."
        )

        return self._make_request(
            prompt=prompt,
            context=signal_context,
            timeout=15.0,
        )

    def suggest_entry(
        self, signal_context: Dict[str, Any], market_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Suggest optimal entry point with reasoning.

        Analyzes bid/ask spread, recent price velocity, support/resistance
        proximity, and VWAP distance to suggest entry timing, optimal SL
        placement, and risk:reward calculation.

        The prompt instructs the LLM to return structured JSON with:
        - suggested_entry: float price for optimal entry
        - suggested_sl: float price with reasoning string
        - timing_recommendation: one of "Enter now — momentum building",
          "Wait 2-3 candles for confirmation", "Do not enter — setup deteriorating"
        - entry_method: one of "market", "limit", "wait_pullback"
        - sl_reasoning: explanation for SL placement
        - risk_reward_default: R:R using scanner entry
        - risk_reward_ai: R:R using AI suggested entry
        - entry_difference_pct: percentage difference between AI and scanner entry
        - entry_difference_highlighted: True if difference > 1%

        Args:
            signal_context: Signal data dictionary containing:
                - symbol: Trading symbol
                - entry_price: Scanner's suggested entry
                - stop_loss: Scanner's suggested SL
                - target_price: Scanner's target
                - confidence_score: Scanner confidence (50-100)
            market_data: Current market data containing:
                - bid: Current bid price
                - ask: Current ask price
                - vwap: Current VWAP level
                - recent_velocity: Price change rate
                - support_levels: List of nearby support levels
                - resistance_levels: List of nearby resistance levels

        Returns:
            Entry suggestion data as dict, or degraded response on failure.

        Implements Requirements: 19.1, 19.2, 19.3, 19.4, 19.5, 19.6
        """
        prompt = (
            "You are a professional trade entry analyst. Analyze the following "
            "signal and current market data to suggest an optimal entry point.\n\n"
            "Return a JSON response with exactly these fields:\n"
            "1. \"suggested_entry\": optimal entry price (float)\n"
            "2. \"suggested_sl\": optimal stop-loss price (float)\n"
            "3. \"sl_reasoning\": explanation for SL placement (e.g., "
            "\"SL below pullback low + buffer\", \"SL at VWAP\", \"Fixed 2% SL\")\n"
            "4. \"timing_recommendation\": one of:\n"
            "   - \"Enter now — momentum building\"\n"
            "   - \"Wait 2-3 candles for confirmation\"\n"
            "   - \"Do not enter — setup deteriorating\"\n"
            "5. \"entry_method\": one of \"market\", \"limit\", \"wait_pullback\"\n"
            "6. \"reasoning\": 1-2 sentences explaining the suggestion\n\n"
            "Consider these factors in your analysis:\n"
            "- Current bid/ask spread (wider spread = worse entry)\n"
            "- Recent price velocity (fast moves may mean chasing)\n"
            "- Support/resistance proximity (entry near support is better)\n"
            "- VWAP distance (entry near VWAP is lower risk)\n\n"
            "Return ONLY valid JSON, no markdown formatting."
        )

        combined_context = {
            "signal": signal_context,
            "market": market_data,
        }

        response = self._make_request(
            prompt=prompt,
            context=combined_context,
            timeout=15.0,
        )

        # If the request failed (graceful degradation), return the error response
        if response.get("error"):
            return response

        # Enrich the response with calculated risk:reward ratios and
        # entry difference highlighting
        scanner_entry = signal_context.get("entry_price", 0)
        scanner_sl = signal_context.get("stop_loss", 0)
        target = signal_context.get("target_price", 0)
        ai_entry = response.get("suggested_entry", scanner_entry)
        ai_sl = response.get("suggested_sl", scanner_sl)

        # Calculate R:R for both default and AI entries
        if scanner_entry and scanner_sl and target:
            response["risk_reward_default"] = self.calculate_risk_reward(
                scanner_entry, scanner_sl, target
            )
        if ai_entry and ai_sl and target:
            response["risk_reward_ai"] = self.calculate_risk_reward(
                ai_entry, ai_sl, target
            )

        # Highlight when AI entry differs from scanner entry by > 1%
        if scanner_entry and ai_entry and scanner_entry != 0:
            entry_diff_pct = abs(ai_entry - scanner_entry) / scanner_entry
            response["entry_difference_pct"] = round(entry_diff_pct * 100, 2)
            response["entry_difference_highlighted"] = entry_diff_pct > 0.01
        else:
            response["entry_difference_pct"] = 0.0
            response["entry_difference_highlighted"] = False

        return response

    def analyze_consolidation(
        self, pattern: Dict[str, Any], market_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze consolidation breakout probability with AI.

        Provides breakout probability, predicted direction, expected move,
        and false breakout warnings based on pattern data and market context.

        Context includes: pattern data (range_high, range_low, avg_price,
        candle_count, duration), broader trend direction, volume profile,
        time of day, proximity to key levels.

        False breakout warnings are raised when:
        - Volume is below average during breakout
        - Breakout occurs against the broader trend
        - Consolidation duration is less than 15 minutes

        Args:
            pattern: Consolidation pattern data with keys:
                - range_high: float
                - range_low: float
                - avg_price: float
                - candle_count: int
                - duration_minutes: int
                - volume_avg: float (optional)
                - breakout_volume: float (optional)
            market_context: Broader market context with keys:
                - trend_direction: str ("bullish", "bearish", "neutral")
                - volume_profile: dict (optional)
                - time_of_day: str (optional, e.g. "09:30")
                - key_levels: dict (optional, support/resistance levels)
                - vwap: float (optional)

        Returns:
            AIConsolidationAnalysis data as dict with:
                - breakout_probability: float (0-100)
                - predicted_direction: str ("up" or "down")
                - expected_move_pct: float
                - false_breakout_risk: bool
                - false_breakout_reasons: List[str]
                - assessment: Optional[str]
            Or degraded response on failure.

        Implements Requirements: 20.1, 20.2, 20.3
        """
        # Determine false breakout risk factors locally before calling LLM
        false_breakout_reasons: List[str] = []

        # Check volume below average during breakout (Req 20.3)
        breakout_volume = pattern.get("breakout_volume")
        volume_avg = pattern.get("volume_avg")
        if (
            breakout_volume is not None
            and volume_avg is not None
            and volume_avg > 0
            and breakout_volume < volume_avg
        ):
            false_breakout_reasons.append(
                "Volume below average during breakout"
            )

        # Check breakout against broader trend (Req 20.3)
        trend_direction = market_context.get("trend_direction", "neutral")
        breakout_direction = pattern.get("breakout_direction", "up")
        if (
            trend_direction == "bearish" and breakout_direction == "up"
        ) or (
            trend_direction == "bullish" and breakout_direction == "down"
        ):
            false_breakout_reasons.append(
                "Breakout against broader trend"
            )

        # Check consolidation duration < 15 minutes (Req 20.3)
        duration_minutes = pattern.get("duration_minutes", 0)
        if duration_minutes < 15:
            false_breakout_reasons.append(
                "Consolidation duration less than 15 minutes"
            )

        false_breakout_risk = len(false_breakout_reasons) > 0

        # Build the detailed prompt for LLM analysis
        prompt = (
            "Analyze the following consolidation pattern for breakout probability.\n\n"
            "You MUST return a JSON object with these exact fields:\n"
            "- breakout_probability: float (0-100, percentage chance of a valid breakout)\n"
            "- predicted_direction: string (\"up\" or \"down\")\n"
            "- expected_move_pct: float (expected percentage move after breakout, relative to consolidation range)\n"
            "- false_breakout_risk: boolean (true if high risk of false breakout)\n"
            "- false_breakout_reasons: list of strings (reasons for false breakout risk)\n"
            "- assessment: string (brief 1-2 sentence assessment of this consolidation)\n\n"
            "Consider these factors:\n"
            "1. Pattern characteristics (range tightness, candle count, duration)\n"
            "2. Broader market trend direction\n"
            "3. Volume profile during consolidation (decreasing volume = stronger setup)\n"
            "4. Time of day (morning breakouts tend to be stronger)\n"
            "5. Proximity to key levels (VWAP, support/resistance, round numbers)\n\n"
            "False breakout warning conditions:\n"
            "- Volume below average during breakout\n"
            "- Breakout against broader trend direction\n"
            "- Consolidation duration less than 15 minutes\n"
        )

        # Prepare context with all relevant data
        combined_context = {
            "pattern": {
                "range_high": pattern.get("range_high"),
                "range_low": pattern.get("range_low"),
                "avg_price": pattern.get("avg_price"),
                "candle_count": pattern.get("candle_count"),
                "duration_minutes": pattern.get("duration_minutes"),
                "volume_avg": pattern.get("volume_avg"),
                "breakout_volume": pattern.get("breakout_volume"),
                "breakout_direction": pattern.get("breakout_direction"),
            },
            "market": {
                "trend_direction": trend_direction,
                "volume_profile": market_context.get("volume_profile"),
                "time_of_day": market_context.get("time_of_day"),
                "key_levels": market_context.get("key_levels"),
                "vwap": market_context.get("vwap"),
            },
            "local_analysis": {
                "false_breakout_risk": false_breakout_risk,
                "false_breakout_reasons": false_breakout_reasons,
            },
        }

        response = self._make_request(
            prompt=prompt,
            context=combined_context,
        )

        # If the LLM call failed, return a locally-computed fallback
        if response.get("error"):
            # Provide a deterministic fallback based on local analysis
            range_high = pattern.get("range_high", 0)
            range_low = pattern.get("range_low", 0)
            avg_price = pattern.get("avg_price", 1)
            candle_count = pattern.get("candle_count", 0)

            # Basic heuristic: more candles + tighter range + aligned trend = higher probability
            range_pct = ((range_high - range_low) / avg_price * 100) if avg_price > 0 else 0
            base_prob = 50.0

            # Tighter range increases probability
            if range_pct < 10:
                base_prob += 10
            if range_pct < 5:
                base_prob += 10

            # More candles increases probability
            if candle_count >= 10:
                base_prob += 10
            elif candle_count >= 6:
                base_prob += 5

            # Duration >= 15 min increases probability
            if duration_minutes >= 15:
                base_prob += 5

            # Aligned with trend increases probability
            if (trend_direction == "bullish" and breakout_direction == "up") or (
                trend_direction == "bearish" and breakout_direction == "down"
            ):
                base_prob += 10

            # False breakout risk decreases probability
            base_prob -= len(false_breakout_reasons) * 10

            # Clamp to 0-100
            base_prob = max(0.0, min(100.0, base_prob))

            # Predicted direction from breakout direction or trend
            predicted_direction = breakout_direction if breakout_direction in ("up", "down") else (
                "up" if trend_direction == "bullish" else "down"
            )

            # Expected move: proportion of consolidation range
            expected_move_pct = range_pct * 0.5 if range_pct > 0 else 2.0

            return {
                "breakout_probability": base_prob,
                "predicted_direction": predicted_direction,
                "expected_move_pct": round(expected_move_pct, 2),
                "false_breakout_risk": false_breakout_risk,
                "false_breakout_reasons": false_breakout_reasons,
                "assessment": (
                    "AI unavailable — local heuristic analysis used. "
                    f"{'High false breakout risk.' if false_breakout_risk else 'Pattern looks reasonable.'}"
                ),
            }

        # If LLM responded, ensure false breakout fields are correct
        # (merge local analysis with LLM response)
        if isinstance(response, dict) and not response.get("error"):
            # Ensure local false breakout reasons are included
            llm_reasons = response.get("false_breakout_reasons", [])
            merged_reasons = list(set(false_breakout_reasons + llm_reasons))
            response["false_breakout_reasons"] = merged_reasons
            response["false_breakout_risk"] = len(merged_reasons) > 0

        return response

    def rank_consolidations(
        self, patterns: List[Dict[str, Any]], market_context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Rank multiple consolidation patterns by breakout probability.

        Calls analyze_consolidation for each pattern, then sorts by
        breakout_probability descending. The highest probability pattern
        is marked as "best_trade": True.

        Args:
            patterns: List of consolidation pattern dictionaries.
            market_context: Broader market context (shared across all patterns).

        Returns:
            List of dicts sorted by breakout_probability descending.
            Each dict contains the original pattern data merged with
            analysis results. The top entry has "best_trade": True.

        Implements Requirements: 20.4
        """
        if not patterns:
            return []

        ranked: List[Dict[str, Any]] = []

        for pattern in patterns:
            analysis = self.analyze_consolidation(pattern, market_context)

            # Build a combined result with pattern info + analysis
            entry: Dict[str, Any] = {
                "pattern": pattern,
                "analysis": analysis,
                "breakout_probability": analysis.get("breakout_probability", 0.0),
                "predicted_direction": analysis.get("predicted_direction", "up"),
                "expected_move_pct": analysis.get("expected_move_pct", 0.0),
                "false_breakout_risk": analysis.get("false_breakout_risk", False),
                "false_breakout_reasons": analysis.get("false_breakout_reasons", []),
                "assessment": analysis.get("assessment"),
                "best_trade": False,
            }
            ranked.append(entry)

        # Sort by breakout_probability descending
        ranked.sort(key=lambda x: x["breakout_probability"], reverse=True)

        # Mark the top one as best trade
        if ranked:
            ranked[0]["best_trade"] = True

        return ranked

    def assess_breakout(
        self, pattern: Dict[str, Any], breakout_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Provide real-time assessment when a breakout occurs.

        Evaluates the breakout quality based on volume, trend alignment,
        and pattern characteristics to provide one of three assessments:
        - "Confirmed breakout — volume supports"
        - "Suspicious — low volume, wait for retest"
        - "False breakout likely — avoid"

        Args:
            pattern: The consolidation pattern data with keys:
                - range_high: float
                - range_low: float
                - avg_price: float
                - candle_count: int
                - duration_minutes: int
                - volume_avg: float (average volume during consolidation)
            breakout_data: Real-time breakout event data with keys:
                - breakout_price: float
                - breakout_volume: float
                - direction: str ("up" or "down")
                - time: str (optional, time of breakout)

        Returns:
            Dict with:
                - assessment: str (one of the three predefined assessments)
                - confidence: float (0-100)
                - details: str (brief reasoning)

        Implements Requirements: 20.5
        """
        breakout_volume = breakout_data.get("breakout_volume", 0)
        volume_avg = pattern.get("volume_avg", 0)
        direction = breakout_data.get("direction", "up")
        duration_minutes = pattern.get("duration_minutes", 0)
        trend_direction = breakout_data.get("trend_direction", "neutral")

        # Evaluate breakout quality
        volume_supports = (
            volume_avg > 0 and breakout_volume >= volume_avg
        )
        trend_aligned = (
            (trend_direction == "bullish" and direction == "up")
            or (trend_direction == "bearish" and direction == "down")
            or trend_direction == "neutral"
        )
        duration_sufficient = duration_minutes >= 15

        # Count positive factors
        positive_factors = sum([volume_supports, trend_aligned, duration_sufficient])

        # Determine assessment
        if positive_factors >= 3 or (volume_supports and trend_aligned):
            assessment = "Confirmed breakout — volume supports"
            confidence = 75.0 + (positive_factors * 5)
        elif not volume_supports and not trend_aligned:
            assessment = "False breakout likely — avoid"
            confidence = 70.0
        else:
            assessment = "Suspicious — low volume, wait for retest"
            confidence = 50.0 + (positive_factors * 10)

        # Build details
        details_parts: List[str] = []
        if volume_supports:
            details_parts.append("breakout volume exceeds average")
        else:
            details_parts.append("breakout volume below average")

        if trend_aligned:
            details_parts.append("aligned with broader trend")
        else:
            details_parts.append("against broader trend")

        if duration_sufficient:
            details_parts.append(f"consolidation held {duration_minutes} min")
        else:
            details_parts.append(f"short consolidation ({duration_minutes} min)")

        # Clamp confidence
        confidence = max(0.0, min(100.0, confidence))

        # Try LLM for richer assessment (non-blocking fallback)
        prompt = (
            "Assess this breakout event in real-time.\n"
            "Determine if this is: 'Confirmed breakout — volume supports', "
            "'Suspicious — low volume, wait for retest', or "
            "'False breakout likely — avoid'.\n\n"
            "Return JSON with: assessment (string), confidence (float 0-100), details (string)."
        )

        combined_context = {
            "pattern": pattern,
            "breakout": breakout_data,
            "local_assessment": {
                "volume_supports": volume_supports,
                "trend_aligned": trend_aligned,
                "duration_sufficient": duration_sufficient,
            },
        }

        llm_response = self._make_request(
            prompt=prompt,
            context=combined_context,
        )

        # If LLM responded successfully, use its assessment
        if isinstance(llm_response, dict) and not llm_response.get("error"):
            # Validate the assessment is one of the allowed values
            llm_assessment = llm_response.get("assessment", "")
            valid_assessments = [
                "Confirmed breakout — volume supports",
                "Suspicious — low volume, wait for retest",
                "False breakout likely — avoid",
            ]
            if llm_assessment in valid_assessments:
                return {
                    "assessment": llm_assessment,
                    "confidence": llm_response.get("confidence", confidence),
                    "details": llm_response.get("details", "; ".join(details_parts)),
                }

        # Fallback to local assessment
        return {
            "assessment": assessment,
            "confidence": confidence,
            "details": "; ".join(details_parts),
        }

    def _detect_exit_warnings(
        self, position: Dict[str, Any], market_data: Dict[str, Any]
    ) -> List[str]:
        """Detect market conditions that warrant exit warnings.

        Performs local analysis for the following conditions (Requirement 21.3):
        1. Momentum divergences — price making new highs/lows but MACD not confirming
        2. Volume drying up — current volume significantly below average
        3. Approaching key support/resistance levels
        4. Theta decay acceleration — options time decay concern
        5. Broader market trend reversals

        Args:
            position: Position data with entry_price, current_price, option_type, etc.
            market_data: Market indicators (MACD, volume, trend, key_levels, etc.).

        Returns:
            List of warning strings for detected conditions.
        """
        warnings: List[str] = []

        # 1. Momentum divergence detection
        macd = market_data.get("macd", {})
        if isinstance(macd, dict):
            histogram = macd.get("histogram", 0)
            prev_histogram = macd.get("prev_histogram", 0)
            current_price = position.get("current_price", 0)
            entry_price = position.get("entry_price", 0)
            option_type = position.get("option_type", "CE")

            # For CE (long): price up but MACD histogram declining = bearish divergence
            if option_type == "CE" and current_price > entry_price:
                if histogram < prev_histogram and prev_histogram > 0:
                    warnings.append(
                        "Momentum divergence — price rising but MACD histogram declining"
                    )
            # For PE (short): price down but MACD histogram rising = bullish divergence
            elif option_type == "PE" and current_price > entry_price:
                if histogram > prev_histogram and prev_histogram < 0:
                    warnings.append(
                        "Momentum divergence — underlying falling but MACD histogram rising"
                    )

        # 2. Volume drying up
        volume = market_data.get("volume")
        volume_avg = market_data.get("volume_avg")
        if volume is not None and volume_avg is not None and volume_avg > 0:
            volume_ratio = volume / volume_avg
            if volume_ratio < 0.5:
                warnings.append(
                    "Volume drying up — current volume below 50% of average, possible exhaustion"
                )

        # 3. Approaching key support/resistance
        key_levels = market_data.get("key_levels", {})
        current_price = position.get("current_price", 0)
        option_type = position.get("option_type", "CE")

        if isinstance(key_levels, dict) and current_price > 0:
            resistance_levels = key_levels.get("resistance", [])
            support_levels = key_levels.get("support", [])

            # For CE positions, check approaching resistance
            if option_type == "CE" and resistance_levels:
                for level in resistance_levels:
                    if isinstance(level, (int, float)) and level > 0:
                        distance_pct = (level - current_price) / current_price * 100
                        if 0 < distance_pct < 1.0:
                            warnings.append(
                                f"Approaching key resistance at {level} — less than 1% away"
                            )
                            break

            # For PE positions, check approaching support
            if option_type == "PE" and support_levels:
                for level in support_levels:
                    if isinstance(level, (int, float)) and level > 0:
                        distance_pct = (current_price - level) / current_price * 100
                        if 0 < distance_pct < 1.0:
                            warnings.append(
                                f"Approaching key support at {level} — less than 1% away"
                            )
                            break

        # 4. Theta decay acceleration
        time_held_minutes = position.get("time_held_minutes", 0)
        days_to_expiry = market_data.get("days_to_expiry")
        if days_to_expiry is not None and days_to_expiry <= 1:
            warnings.append(
                "Theta decay accelerating — expiry day, time value decaying rapidly"
            )
        elif days_to_expiry is not None and days_to_expiry <= 2 and time_held_minutes > 120:
            warnings.append(
                "Theta decay concern — near expiry with extended holding time"
            )

        # 5. Broader market trend reversal
        trend = market_data.get("trend", "neutral")
        option_type = position.get("option_type", "CE")
        if option_type == "CE" and trend == "bearish":
            warnings.append(
                "Broader market trend reversal — market turning bearish against CE position"
            )
        elif option_type == "PE" and trend == "bullish":
            warnings.append(
                "Broader market trend reversal — market turning bullish against PE position"
            )

        return warnings

    def _compute_local_exit_recommendation(
        self, position: Dict[str, Any], market_data: Dict[str, Any], warnings: List[str]
    ) -> Dict[str, Any]:
        """Compute a local (non-LLM) exit recommendation based on detected conditions.

        Used as a fallback when the LLM is unavailable. Applies rule-based logic
        to determine the best exit action from detected warnings and position state.

        This method is ADVISORY ONLY — it never executes any trade.

        Args:
            position: Position data.
            market_data: Market data.
            warnings: List of detected warning conditions.

        Returns:
            Dictionary with action, reasoning, confidence, and warnings.
        """
        num_warnings = len(warnings)

        # Default to hold if no concerns
        if num_warnings == 0:
            return {
                "action": "hold",
                "reasoning": "No significant exit signals detected. Trend appears intact.",
                "confidence": 60,
                "warnings": [],
            }

        # High-confidence exit_now: 3+ warnings or critical conditions
        critical_keywords = ["trend reversal", "Theta decay accelerating"]
        has_critical = any(
            any(kw.lower() in w.lower() for kw in critical_keywords)
            for w in warnings
        )

        if num_warnings >= 3 or (num_warnings >= 2 and has_critical):
            return {
                "action": "exit_now",
                "reasoning": f"Multiple exit signals detected ({num_warnings} warnings). Risk outweighs potential reward.",
                "confidence": 85,
                "warnings": warnings,
            }

        # Moderate concern: tighten stop or book partial
        if has_critical or num_warnings == 2:
            # Check if in profit to recommend book_partial
            entry_price = position.get("entry_price", 0)
            current_price = position.get("current_price", 0)
            option_type = position.get("option_type", "CE")
            in_profit = (
                (current_price > entry_price) if option_type == "CE"
                else (current_price > entry_price)  # For option premium
            )
            unrealized_pnl = position.get("unrealized_pnl", 0)

            if in_profit and unrealized_pnl > 0:
                return {
                    "action": "book_partial",
                    "reasoning": "Multiple concerns detected while in profit. Consider booking partial gains.",
                    "confidence": 70,
                    "warnings": warnings,
                }
            else:
                return {
                    "action": "tighten_stop",
                    "reasoning": "Warning signals detected. Tightening stop to reduce risk exposure.",
                    "confidence": 65,
                    "warnings": warnings,
                }

        # Single warning: tighten stop
        return {
            "action": "tighten_stop",
            "reasoning": f"Caution signal detected: {warnings[0]}. Consider tightening stop.",
            "confidence": 55,
            "warnings": warnings,
        }

    def evaluate_exit(
        self, position: Dict[str, Any], market_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate whether to hold, tighten, or exit an open position.

        Uses local detection logic combined with LLM analysis to provide
        one of: hold, tighten_stop, book_partial, exit_now.

        Detection logic actively checks for (Requirement 21.3):
        1. Momentum divergences — price vs MACD histogram
        2. Volume drying up — current volume below 50% of average
        3. Approaching key support/resistance — within 1%
        4. Theta decay acceleration — near or on expiry day
        5. Broader market trend reversals — market direction vs position

        This method is ADVISORY ONLY — it never auto-executes any trade.
        All exit actions require explicit trader confirmation (Requirement 21.6).

        Evaluation runs on a 30-second cycle (EXIT_EVALUATION_INTERVAL).

        Args:
            position: Current position data including:
                - entry_price: float — position entry price
                - current_price: float — current market price
                - stop_loss: float — current stop loss level
                - target: float — target price
                - unrealized_pnl: float — current unrealized P&L
                - time_held_minutes: int — how long position has been open
                - symbol: str — trading symbol
                - quantity: int — position quantity
                - option_type: str — CE/PE
            market_data: Current market data including:
                - macd: dict — MACD signal and histogram values
                    - histogram: float — current histogram value
                    - prev_histogram: float — previous histogram value
                - momentum: float — momentum indicator value
                - volume: float — current volume
                - volume_avg: float — average volume
                - trend: str — broader market trend direction
                - key_levels: dict — support/resistance levels
                    - support: list[float]
                    - resistance: list[float]
                - ema_20: float — 20-period EMA value
                - vwap: float — VWAP value
                - days_to_expiry: int — days until option expiry

        Returns:
            Dictionary with exit recommendation data:
                - action: str — one of "hold", "tighten_stop", "book_partial", "exit_now"
                - reasoning: str — 1-2 sentence explanation
                - confidence: float — 0-100
                - warnings: list[str] — detected market concerns
            Or degraded response on failure.

        Implements Requirements: 21.1, 21.2, 21.3, 21.6
        """
        # Step 1: Run local detection for exit warnings (Requirement 21.3)
        detected_warnings = self._detect_exit_warnings(position, market_data)

        # Step 2: Attempt LLM-powered analysis for richer recommendation
        prompt = (
            "You are an AI exit advisor for an options trader. Analyze the open position "
            "and current market conditions below, then recommend ONE of these actions:\n"
            "- 'hold': Trend remains intact, no action needed.\n"
            "- 'tighten_stop': Move stop loss closer to lock in gains.\n"
            "- 'book_partial': Book 50% profits at current levels.\n"
            "- 'exit_now': Close the full position immediately.\n\n"
            "IMPORTANT DETECTION RULES — actively look for:\n"
            "1. Momentum divergences: price making new highs/lows but MACD not confirming\n"
            "2. Volume drying up: declining volume suggesting exhaustion\n"
            "3. Approaching key resistance (for longs) or support (for shorts)\n"
            "4. Theta decay acceleration: options losing value faster as expiry nears\n"
            "5. Broader market trend reversals: index turning against position direction\n\n"
            "CRITICAL CONSTRAINT: This is a RECOMMENDATION ONLY. You must NEVER suggest "
            "auto-execution. The trader must manually confirm any exit action.\n\n"
            "Respond in valid JSON with exactly these fields:\n"
            '{\n'
            '  "action": "<hold|tighten_stop|book_partial|exit_now>",\n'
            '  "reasoning": "<1-2 sentence explanation>",\n'
            '  "confidence": <0-100 integer>,\n'
            '  "warnings": ["<list of detected concerns, if any>"]\n'
            '}\n'
        )

        combined_context = {
            "position": position,
            "market": market_data,
            "detected_warnings": detected_warnings,
        }

        response = self._make_request(
            prompt=prompt,
            context=combined_context,
        )

        # Step 3: If LLM failed, use local fallback recommendation
        if isinstance(response, dict) and response.get("error"):
            return self._compute_local_exit_recommendation(
                position, market_data, detected_warnings
            )

        # Step 4: Merge local warnings into the LLM response
        if isinstance(response, dict):
            llm_warnings = response.get("warnings", [])
            if not isinstance(llm_warnings, list):
                llm_warnings = []
            # Merge unique warnings from local detection
            merged_warnings = list(set(llm_warnings + detected_warnings))
            response["warnings"] = merged_warnings

            # Validate action field
            action = response.get("action", "hold")
            if action not in VALID_EXIT_ACTIONS:
                response["action"] = "hold"

            # Ensure confidence is a number in range 0-100
            confidence = response.get("confidence", 50.0)
            if not isinstance(confidence, (int, float)):
                confidence = 50.0
            response["confidence"] = float(max(0.0, min(100.0, float(confidence))))

        return response

    def generate_narrative(
        self, session_type: str, market_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate market context narrative with AI.

        Produces session-specific market commentary including key points,
        directional bias, expected range, and key support/resistance levels.

        Session types and their times:
        - "morning_brief": 9:15 IST — covers overnight global cues, previous day summary
        - "mid_morning": 10:30 IST — first hour trends, momentum shifts
        - "lunch": 12:30 IST — mid-day assessment, volume patterns
        - "afternoon": 14:00 IST — closing session outlook, institutional activity

        Args:
            session_type: One of "morning_brief", "mid_morning", "lunch", "afternoon".
            market_data: Current market data including:
                - previous_day_summary: str
                - overnight_global_cues: str
                - index_data: dict (NIFTY, BANKNIFTY prices/changes)
                - vix: float
                - fii_dii_activity: dict

        Returns:
            AIMarketNarrative data as dict, or degraded response on failure.

        Implements Requirements: 22.1, 22.2, 22.3, 22.4, 22.5
        """
        # Validate session_type
        if session_type not in VALID_SESSION_TYPES:
            session_type = "morning_brief"

        session_descriptions = {
            "morning_brief": "pre-market/opening brief at 9:15 IST covering overnight events and day outlook",
            "mid_morning": "mid-morning update at 10:30 IST covering first hour trends and momentum",
            "lunch": "lunch break update at 12:30 IST covering mid-day assessment and volume",
            "afternoon": "afternoon session update at 14:00 IST covering closing outlook and institutional activity",
        }

        prompt = f"""You are a professional market analyst providing a {session_descriptions[session_type]} for an Indian equity/options trader.

Analyze the provided market data and generate a concise, actionable market narrative.

IMPORTANT CONSTRAINTS:
- Provide EXACTLY 5 or fewer key points as bullet items. Never exceed 5 key points.
- Each key point must be concise (1-2 sentences max).
- Bias must be exactly one of: "bullish", "bearish", or "neutral"
- Focus on actionable insights for intraday options trading

Return your response as a JSON object with these exact fields:
{{
    "session_type": "{session_type}",
    "key_points": ["point 1", "point 2", ...],  // MAX 5 items
    "bias": "bullish" | "bearish" | "neutral",
    "expected_range": {{"low": <float>, "high": <float>}},
    "key_levels": {{"support": [<float>, ...], "resistance": [<float>, ...]}},
    "detailed_analysis": "<optional 2-3 paragraph detailed analysis>"
}}

Context to analyze:
- Previous day summary: {market_data.get('previous_day_summary', 'Not available')}
- Overnight global cues: {market_data.get('overnight_global_cues', 'Not available')}
- Current VIX: {market_data.get('vix', 'Not available')}
- FII/DII Activity: {market_data.get('fii_dii_activity', 'Not available')}

Focus on: RBI announcements, F&O expiry dynamics, FII/DII activity, sector rotation, and any significant events affecting intraday trading."""

        context = {
            "session_type": session_type,
            "market": market_data,
        }

        response = self._make_request(
            prompt=prompt,
            context=context,
        )

        # If error response from _make_request, return as-is
        if isinstance(response, dict) and response.get("error"):
            return response

        # Parse and validate via format_narrative
        try:
            narrative = format_narrative(response)
            return narrative.model_dump()
        except Exception as e:
            logger.warning("Failed to format narrative response: %s", str(e))
            return response

    def review_trade(
        self, trade: Dict[str, Any], market_history: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Review completed trade with improvement suggestions.

        Analyzes entry timing, exit timing, position sizing, and risk
        management to assign an overall letter grade and provide specific
        feedback for each dimension.  Compares actual execution against
        what an optimal execution would have achieved, and identifies
        recurring behavioral patterns.

        Args:
            trade: Completed trade data including:
                - symbol: str — trading symbol
                - entry_price: float — actual entry price
                - exit_price: float — actual exit price
                - entry_time: str — timestamp of entry
                - exit_time: str — timestamp of exit
                - quantity: int — position size
                - option_type: str — CE/PE
                - stop_loss: float — configured stop loss
                - target: float — configured target
                - pnl: float — realized P&L
                - exit_reason: str — why the trade was exited
                - confidence_score: float — original signal confidence
            market_history: Historical market data during the trade:
                - candles: list — OHLCV candles during trade period
                - optimal_entry: float (optional) — best available entry
                - optimal_exit: float (optional) — best available exit
                - trend_during_trade: str — trend direction during trade
                - volume_profile: dict (optional) — volume analysis
                - key_levels: dict (optional) — S/R levels active during trade

        Returns:
            AITradeReview data as dict with:
                - grade: str (A/B/C/D/F)
                - entry_feedback: str
                - exit_feedback: str
                - sizing_feedback: str
                - risk_feedback: str
                - optimal_comparison: str
                - patterns_identified: list[str]
            Or degraded response on failure.

        Implements Requirements: 23.1, 23.2, 23.3, 23.4, 23.5
        """
        prompt = """You are a professional trading coach reviewing a completed options trade. Analyze the trade execution quality and provide specific, actionable feedback.

GRADING CRITERIA:
- A: Excellent execution — entry/exit timing near optimal, proper sizing, risk well-managed
- B: Good execution — minor timing issues but overall solid risk management
- C: Average execution — noticeable timing or sizing issues, room for improvement
- D: Below average — significant execution errors, poor risk management
- F: Poor execution — major errors, excessive risk taken, fundamental strategy violations

ANALYSIS REQUIREMENTS:
1. Entry Timing: Was the entry well-timed? Were there better candles to enter on? Did the trader chase the move or enter at support/resistance?
2. Exit Timing: Was the exit optimal? Did they exit too early (leaving profit on the table) or too late (giving back gains)? Was the stop loss appropriate?
3. Position Sizing: Was the position size appropriate for the account capital and risk level? Was it too large given the stop loss distance?
4. Risk Management: Was the risk:reward ratio favorable? Did they respect their stop loss? Was the max loss acceptable?
5. Optimal Comparison: Compare actual entry/exit vs what optimal execution would have achieved. Quantify the difference.
6. Pattern Identification: Identify behavioral patterns (e.g., "exits too early on winners", "chases entries", "oversizes on low-confidence signals")

Return a JSON object with exactly these fields:
{
    "grade": "A" | "B" | "C" | "D" | "F",
    "entry_feedback": "<specific feedback on entry timing and quality>",
    "exit_feedback": "<specific feedback on exit timing and quality>",
    "sizing_feedback": "<feedback on position sizing appropriateness>",
    "risk_feedback": "<feedback on risk management quality>",
    "optimal_comparison": "<comparison of actual vs optimal execution with quantified difference>",
    "patterns_identified": ["<pattern 1>", "<pattern 2>", ...]
}

Be specific and quantitative where possible. Reference actual price levels and candle patterns from the data."""

        context = {
            "trade": trade,
            "market_history": market_history,
        }

        response = self._make_request(
            prompt=prompt,
            context=context,
        )

        # If error response from _make_request, return as-is
        if isinstance(response, dict) and response.get("error"):
            return response

        # Parse and validate via format_trade_review
        try:
            review = format_trade_review(response)
            return review.model_dump()
        except Exception as e:
            logger.warning("Failed to format trade review response: %s", str(e))
            return response

    def detect_risk_anomalies(
        self, user_state: Dict[str, Any], market_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Detect behavioral anomalies and market risks.

        Combines deterministic rule-based checks (consecutive losses, revenge
        trading, rule violations) with AI-powered market condition analysis.

        Rule-based checks (no LLM call needed):
        - Break suggestion: 3+ consecutive losses → severity: warning, category: behavioral
        - Revenge trading: new trade within 5 min of loss on same/correlated symbol
          → severity: critical, category: behavioral
        - Risk rule violations: max trades exceeded, trading outside hours,
          daily loss limit breached → severity: critical, category: rule_violation,
          requires_acknowledgment: True

        AI-powered checks (uses LLM when available):
        - Market condition warnings: elevated VIX, sudden volume drops,
          gap openings, unfavorable conditions

        Args:
            user_state: User's recent trading behavior and state, including:
                - consecutive_losses (int): Number of consecutive losing trades
                - last_loss_time_minutes (float): Minutes since last loss
                - same_or_correlated_symbol (bool): Whether new trade is on
                    same/correlated symbol as last loss
                - current_trades (int): Number of trades taken today
                - max_trades (int): Maximum allowed trades per day
                - current_hour (float): Current time as hours (e.g., 9.25)
                - trading_start_hour (float): Configured start hour
                - trading_end_hour (float): Configured end hour
                - daily_loss (float): Current day's realized loss
                - loss_limit (float): Maximum allowed daily loss
            market_data: Current market conditions, including:
                - vix (float): Current VIX level
                - vix_change_pct (float): VIX change percentage
                - volume_ratio (float): Current vs average volume ratio
                - gap_pct (float): Gap open percentage
                - is_expiry_day (bool): Whether today is an expiry day

        Returns:
            Dictionary with:
                - warnings: List of AIRiskWarning-compatible dicts
                - warning_count: Total number of warnings
                - has_critical: Whether any critical warnings exist
                - requires_acknowledgment: Whether any warning requires ack
            Or degraded response with error=True on failure.

        Implements Requirements: 24.1, 24.2, 24.3, 24.4, 24.5, 24.6
        """
        from src.services.risk_detection import (
            should_suggest_break,
            is_revenge_trading,
            detect_rule_violations,
        )

        warnings: List[Dict[str, Any]] = []

        # --- Deterministic behavioral checks (no LLM needed) ---

        # 1. Break suggestion: 3+ consecutive losses (Req 24.3)
        consecutive_losses = user_state.get("consecutive_losses", 0)
        if should_suggest_break(consecutive_losses):
            warnings.append({
                "severity": "warning",
                "message": (
                    f"Consider taking a break — {consecutive_losses} consecutive "
                    f"losses detected"
                ),
                "category": "behavioral",
                "requires_acknowledgment": False,
            })

        # 2. Revenge trading detection (Req 24.5)
        last_loss_time_minutes = user_state.get("last_loss_time_minutes")
        same_or_correlated = user_state.get("same_or_correlated_symbol", False)
        if last_loss_time_minutes is not None and is_revenge_trading(
            last_loss_time_minutes, same_or_correlated
        ):
            warnings.append({
                "severity": "critical",
                "message": (
                    "Potential revenge trading detected — new trade within "
                    f"{last_loss_time_minutes:.1f} minutes of a loss on the "
                    "same or correlated symbol. Consider a cooling-off period."
                ),
                "category": "behavioral",
                "requires_acknowledgment": False,
            })

        # 3. Risk rule violation blocking (Req 24.4)
        rule_violations = detect_rule_violations(user_state)
        warnings.extend(rule_violations)

        # --- Market condition warnings (deterministic + AI-enhanced) ---

        # 4. Elevated VIX / volatility warning (Req 24.1)
        vix = market_data.get("vix")
        vix_change_pct = market_data.get("vix_change_pct", 0.0)
        if vix is not None and vix > 20:
            warnings.append({
                "severity": "warning",
                "message": (
                    f"Elevated market volatility — VIX at {vix:.1f}"
                    f"{' (spike: +' + f'{vix_change_pct:.1f}%' + ')' if vix_change_pct > 10 else ''}"
                ),
                "category": "market_condition",
                "requires_acknowledgment": False,
            })

        # 5. Sudden volume drop warning (Req 24.1)
        volume_ratio = market_data.get("volume_ratio")
        if volume_ratio is not None and volume_ratio < 0.5:
            warnings.append({
                "severity": "info",
                "message": (
                    f"Low market volume — current volume is {volume_ratio:.0%} "
                    "of average. Breakouts may be unreliable."
                ),
                "category": "market_condition",
                "requires_acknowledgment": False,
            })

        # 6. Gap opening warning (Req 24.1)
        gap_pct = market_data.get("gap_pct")
        if gap_pct is not None and abs(gap_pct) > 1.0:
            direction = "up" if gap_pct > 0 else "down"
            warnings.append({
                "severity": "warning",
                "message": (
                    f"Gap-{direction} opening of {abs(gap_pct):.1f}% detected. "
                    "Initial price action may be volatile."
                ),
                "category": "market_condition",
                "requires_acknowledgment": False,
            })

        # 7. Expiry day warning (Req 24.1)
        is_expiry_day = market_data.get("is_expiry_day", False)
        if is_expiry_day:
            warnings.append({
                "severity": "info",
                "message": (
                    "Expiry day — elevated gamma exposure and theta decay. "
                    "Consider reducing position sizes."
                ),
                "category": "market_condition",
                "requires_acknowledgment": False,
            })

        # 8. AI-enhanced market analysis (optional, non-blocking)
        # Only call LLM if there are no critical rule violations already
        # and if market data is available for deeper analysis
        ai_market_warnings: List[Dict[str, Any]] = []
        if market_data and not any(
            w.get("category") == "rule_violation" for w in warnings
        ):
            try:
                combined_context = {
                    "user_state": user_state,
                    "market": market_data,
                }
                ai_response = self._make_request(
                    prompt=(
                        "You are a risk analyst. Analyze the following market "
                        "conditions and trader state. Identify any additional "
                        "risks not covered by these existing warnings: "
                        "volatility spikes, unfavorable conditions for the "
                        "strategy, unusual market behavior.\n\n"
                        "Return a JSON array of warnings, each with:\n"
                        '- "severity": "info", "warning", or "critical"\n'
                        '- "message": brief description of the risk\n'
                        '- "category": "market_condition"\n'
                        '- "requires_acknowledgment": false\n\n'
                        "If no additional risks are detected, return an empty "
                        "array []. Return ONLY valid JSON."
                    ),
                    context=combined_context,
                )

                # Parse AI response if successful
                if not ai_response.get("error"):
                    if isinstance(ai_response, list):
                        ai_market_warnings = ai_response
                    elif isinstance(ai_response, dict) and "warnings" in ai_response:
                        ai_market_warnings = ai_response.get("warnings", [])
            except Exception:
                # AI market analysis is non-blocking — skip on any error
                logger.debug("AI market condition analysis unavailable, skipping")

        # Add valid AI-derived warnings
        for ai_warning in ai_market_warnings:
            if isinstance(ai_warning, dict) and "message" in ai_warning:
                warnings.append({
                    "severity": ai_warning.get("severity", "info"),
                    "message": ai_warning["message"],
                    "category": ai_warning.get("category", "market_condition"),
                    "requires_acknowledgment": ai_warning.get(
                        "requires_acknowledgment", False
                    ),
                })

        # Build the response
        has_critical = any(w.get("severity") == "critical" for w in warnings)
        requires_ack = any(w.get("requires_acknowledgment") for w in warnings)

        return {
            "warnings": warnings,
            "warning_count": len(warnings),
            "has_critical": has_critical,
            "requires_acknowledgment": requires_ack,
        }
