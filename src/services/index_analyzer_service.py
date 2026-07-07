"""Index Analyzer Service — compares indices with momentum/volume/trend scoring
and recommends trading direction.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

from typing import Dict, List, Optional

from pydantic import BaseModel


# --- Pydantic Models ---


class IndexMetrics(BaseModel):
    """Metrics for a single index with composite scoring."""

    symbol: str  # "SENSEX", "NIFTY 50", "BANK NIFTY"
    current_price: float
    change_1h_pct: float
    change_daily_pct: float
    momentum_score: float  # 0-100
    volume_score: float  # 0-100
    trend_direction: str  # "bullish", "bearish", "neutral"
    composite_score: float  # weighted combination
    data_available: bool


class IndexRecommendation(BaseModel):
    """Trade recommendation based on index analysis."""

    best_index: str
    option_type: str  # "CE" or "PE"
    recommended_strike: float
    strike_step: int  # 50 for NIFTY, 100 for BANKNIFTY/SENSEX
    reasoning: str


# --- Constants ---

# Strike step sizes per index
STRIKE_STEPS: Dict[str, int] = {
    "NIFTY 50": 50,
    "BANK NIFTY": 100,
    "SENSEX": 100,
}

# Trend direction to numeric score mapping
TREND_SCORES: Dict[str, float] = {
    "bullish": 100.0,
    "neutral": 50.0,
    "bearish": 0.0,
}

# Composite score weights
WEIGHT_MOMENTUM = 0.4
WEIGHT_VOLUME = 0.3
WEIGHT_TREND = 0.3


# --- Service ---


class IndexAnalyzerService:
    """Computes index comparison metrics and recommendations."""

    def compute_composite_score(
        self, momentum: float, volume: float, trend: str
    ) -> float:
        """Compute weighted composite score.

        Formula: momentum(40%) + volume(30%) + trend_score(30%)
        - momentum: 0-100 direct numeric value
        - volume: 0-100 direct numeric value
        - trend: "bullish"=100, "neutral"=50, "bearish"=0

        Returns composite score as a float.
        """
        trend_score = TREND_SCORES.get(trend.lower(), 50.0)
        composite = (
            momentum * WEIGHT_MOMENTUM
            + volume * WEIGHT_VOLUME
            + trend_score * WEIGHT_TREND
        )
        return round(composite, 2)

    def recommend_trade(
        self, metrics: List[IndexMetrics]
    ) -> Optional[IndexRecommendation]:
        """Select best index, option type, and strike based on composite score.

        - Filters to only indices with data_available=True
        - Picks the index with the highest composite_score
        - Option type: "CE" if trend_direction is "bullish", else "PE"
        - Strike: nearest ATM at configured step (50 NIFTY, 100 BANKNIFTY/SENSEX)

        Returns None if no indices have data available.
        """
        # Filter to only available indices
        available = [m for m in metrics if m.data_available]
        if not available:
            return None

        # Pick index with highest composite score
        best = max(available, key=lambda m: m.composite_score)

        # Determine option type from trend direction
        option_type = "CE" if best.trend_direction == "bullish" else "PE"

        # Calculate nearest ATM strike
        strike_step = STRIKE_STEPS.get(best.symbol, 100)
        recommended_strike = self._nearest_strike(best.current_price, strike_step)

        # Build reasoning
        reasoning = (
            f"{best.symbol} has the highest composite score ({best.composite_score:.1f}) "
            f"with {best.trend_direction} trend. "
            f"Recommending {option_type} at strike {recommended_strike:.0f}."
        )

        return IndexRecommendation(
            best_index=best.symbol,
            option_type=option_type,
            recommended_strike=recommended_strike,
            strike_step=strike_step,
            reasoning=reasoning,
        )

    def analyze_indices(
        self, market_data: Dict[str, dict]
    ) -> List[IndexMetrics]:
        """Accept raw market data dict per index, compute metrics.

        Args:
            market_data: Dict mapping index symbol to raw data dict.
                Each dict should contain:
                - current_price: float
                - change_1h_pct: float
                - change_daily_pct: float
                - momentum_score: float (0-100)
                - volume_score: float (0-100)
                - trend_direction: str ("bullish"/"bearish"/"neutral")
                - data_available: bool (optional, defaults to True)

        Returns:
            List of IndexMetrics with computed composite scores.
        """
        results: List[IndexMetrics] = []

        for symbol, data in market_data.items():
            data_available = data.get("data_available", True)

            if not data_available:
                # Return metrics with zeroed scores when data is unavailable
                results.append(
                    IndexMetrics(
                        symbol=symbol,
                        current_price=0.0,
                        change_1h_pct=0.0,
                        change_daily_pct=0.0,
                        momentum_score=0.0,
                        volume_score=0.0,
                        trend_direction="neutral",
                        composite_score=0.0,
                        data_available=False,
                    )
                )
                continue

            momentum_score = data.get("momentum_score", 0.0)
            volume_score = data.get("volume_score", 0.0)
            trend_direction = data.get("trend_direction", "neutral")

            composite_score = self.compute_composite_score(
                momentum=momentum_score,
                volume=volume_score,
                trend=trend_direction,
            )

            results.append(
                IndexMetrics(
                    symbol=symbol,
                    current_price=data.get("current_price", 0.0),
                    change_1h_pct=data.get("change_1h_pct", 0.0),
                    change_daily_pct=data.get("change_daily_pct", 0.0),
                    momentum_score=momentum_score,
                    volume_score=volume_score,
                    trend_direction=trend_direction,
                    composite_score=composite_score,
                    data_available=True,
                )
            )

        return results

    @staticmethod
    def _nearest_strike(price: float, step: int) -> float:
        """Round price to the nearest strike step (ATM strike).

        For example:
        - price=22437, step=50 → 22450
        - price=47230, step=100 → 47200
        - price=72550, step=100 → 72600
        """
        return round(price / step) * step
