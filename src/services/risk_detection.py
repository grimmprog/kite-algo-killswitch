"""Pure logic functions for risk detection and behavioral anomaly analysis.

Implements the deterministic risk detection rules for:
- Break suggestion after consecutive losses (Requirement 24.3)
- Revenge trading detection (Requirement 24.5)
- Risk rule violation blocking (Requirement 24.4)
"""

from typing import List, Dict, Any


def should_suggest_break(consecutive_losses: int) -> bool:
    """Determine if a break suggestion should be shown.

    Returns True iff the trader has 3 or more consecutive losses.

    Args:
        consecutive_losses: Number of consecutive losing trades.

    Returns:
        True if a break should be suggested, False otherwise.
    """
    return consecutive_losses >= 3


def is_revenge_trading(last_loss_time_minutes: float, same_or_correlated_symbol: bool) -> bool:
    """Detect potential revenge trading behavior.

    Returns True iff the trader is entering a new trade within 5 minutes
    of a loss on the same or correlated symbol.

    Args:
        last_loss_time_minutes: Minutes since the last losing trade.
        same_or_correlated_symbol: Whether the new trade is on the same
            or a correlated symbol as the losing trade.

    Returns:
        True if revenge trading pattern is detected, False otherwise.
    """
    return last_loss_time_minutes <= 5.0 and same_or_correlated_symbol


def detect_rule_violations(user_state: dict) -> List[Dict[str, Any]]:
    """Detect risk rule violations that require blocking warnings.

    Checks the user's current trading state against their configured rules
    and returns a list of violations. Each violation requires explicit
    acknowledgment before the trader can proceed.

    Violations checked:
    - Exceeding max trades per day
    - Trading outside configured trading hours
    - Exceeding daily loss limit

    Args:
        user_state: Dictionary containing:
            - current_trades (int): Number of trades taken today
            - max_trades (int): Maximum allowed trades per day
            - current_hour (float): Current time as hours (e.g., 9.25 for 9:15)
            - trading_start_hour (float): Configured start hour
            - trading_end_hour (float): Configured end hour
            - daily_loss (float): Current day's realized loss (positive value)
            - loss_limit (float): Maximum allowed daily loss (positive value)

    Returns:
        List of violation dicts with keys:
            - severity (str): "warning" or "critical"
            - message (str): Description of the violation
            - category (str): "rule_violation"
            - requires_acknowledgment (bool): Always True for violations
    """
    violations: List[Dict[str, Any]] = []

    # Check max trades exceeded
    current_trades = user_state.get("current_trades", 0)
    max_trades = user_state.get("max_trades", 10)
    if current_trades >= max_trades:
        violations.append({
            "severity": "warning",
            "message": f"Max trades per day exceeded ({current_trades}/{max_trades})",
            "category": "rule_violation",
            "requires_acknowledgment": True,
        })

    # Check trading outside configured hours
    current_hour = user_state.get("current_hour")
    trading_start_hour = user_state.get("trading_start_hour")
    trading_end_hour = user_state.get("trading_end_hour")
    if (
        current_hour is not None
        and trading_start_hour is not None
        and trading_end_hour is not None
    ):
        if current_hour < trading_start_hour or current_hour > trading_end_hour:
            violations.append({
                "severity": "warning",
                "message": "Trading outside configured trading hours",
                "category": "rule_violation",
                "requires_acknowledgment": True,
            })

    # Check daily loss limit exceeded
    daily_loss = user_state.get("daily_loss", 0.0)
    loss_limit = user_state.get("loss_limit")
    if loss_limit is not None and loss_limit > 0 and daily_loss >= loss_limit:
        violations.append({
            "severity": "critical",
            "message": f"Daily loss limit exceeded (₹{daily_loss:.0f}/₹{loss_limit:.0f})",
            "category": "rule_violation",
            "requires_acknowledgment": True,
        })

    return violations
