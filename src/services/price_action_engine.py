"""Price Action Engine — Vectorized Multi-Touch Breakout/Breakdown Detection
with Dynamic ATR Trailing Stop-Loss.

Detects structural multi-touch breakout/breakdown patterns at key levels using:
- Rolling resistance/support zone detection with adaptive tolerance
- Accumulated touch counting with compression rule validation
- High-volume fakeout filtering via volume exhaustion threshold
- Ratcheting ATR trailing stop (Chandelier Exit variation)

All indicator calculations use NumPy vectorization and Pandas .rolling() methods
for maximum performance over large datasets.

Architecture:
    - detect_signals(): Main entry point — returns DataFrame with signal columns
    - TradeStateManager: Tracks active positions with non-retreating trailing stops

Integrates with existing:
    - pivot_breakout_service.py (pivot level calculations)
    - signal_pipeline.py (signal persistence and WebSocket relay)
    - scanner_service.py (complementary scan approach)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# --- Constants / Hyperparameters ---

DEFAULT_LOOKBACK = 20          # Rolling window for resistance/support detection
DEFAULT_TOLERANCE = 0.001      # 0.1% tolerance for level touches
DEFAULT_VOL_MULTIPLIER = 1.5   # Volume must exceed SMA * this to confirm breakout
DEFAULT_ATR_PERIOD = 14        # ATR lookback period
DEFAULT_ATR_MULTIPLIER = 2.5   # ATR multiplier for trailing stop distance
MIN_TOUCHES_FOR_SIGNAL = 3     # Minimum touches before breakout is valid


# --- Enums ---

class SignalDirection(IntEnum):
    """Breakout signal direction values for DataFrame column."""
    BUY_CALL = 1     # Bullish breakout — buy call option
    NONE = 0         # No signal
    BUY_PUT = -1     # Bearish breakdown — buy put option


# --- Pydantic Models ---

class EngineConfig(BaseModel):
    """Configuration for the Price Action Engine hyperparameters.

    Attributes:
        lookback: Rolling window for resistance/support detection.
        tolerance: Percentage tolerance for level touches (0.001 = 0.1%).
        vol_multiplier: Volume exhaustion threshold multiplier over SMA.
        atr_period: ATR calculation lookback period.
        atr_multiplier: Multiplier for ATR trailing stop distance.
        min_touches: Minimum accumulated touches before a breakout is valid.
    """
    lookback: int = Field(default=DEFAULT_LOOKBACK, ge=5, le=100)
    tolerance: float = Field(default=DEFAULT_TOLERANCE, gt=0, le=0.05)
    vol_multiplier: float = Field(default=DEFAULT_VOL_MULTIPLIER, ge=1.0, le=5.0)
    atr_period: int = Field(default=DEFAULT_ATR_PERIOD, ge=5, le=50)
    atr_multiplier: float = Field(default=DEFAULT_ATR_MULTIPLIER, ge=1.0, le=10.0)
    min_touches: int = Field(default=MIN_TOUCHES_FOR_SIGNAL, ge=2, le=10)


class BreakoutSignalResult(BaseModel):
    """A single detected breakout/breakdown signal with full context.

    Attributes:
        index: DataFrame row index where the signal was detected.
        direction: 1 for bullish breakout, -1 for bearish breakdown.
        level_value: The price level that was broken.
        touch_count: Number of accumulated touches before the break.
        breakout_price: Close price at breakout candle.
        volume_confirmed: Whether volume exhaustion threshold was met.
        atr_value: ATR at breakout candle.
        initial_stop_loss: Initial trailing stop value.
        confidence_score: Overall signal confidence (50-100).
        timestamp: ISO timestamp of the breakout candle.
    """
    index: int
    direction: int = Field(ge=-1, le=1)
    level_value: float
    touch_count: int
    breakout_price: float
    volume_confirmed: bool
    atr_value: float
    initial_stop_loss: float
    confidence_score: float = Field(ge=50, le=100)
    timestamp: str = ""


# --- Core Engine ---

def detect_signals(
    df: pd.DataFrame,
    config: Optional[EngineConfig] = None,
) -> pd.DataFrame:
    """Main entry point: detect multi-touch breakout/breakdown signals.

    Adds the following columns to the DataFrame:
    - Is_Resistance_Touch: 1 if candle touches rolling resistance zone, else 0
    - Is_Support_Touch: 1 if candle touches rolling support zone, else 0
    - Accumulated_Touches: Running count of touches within lookback window
    - Breakout_Signal: 1 (Buy Call), -1 (Buy Put), or 0 (None)
    - Dynamic_Trailing_SL: Float trailing stop value (NaN if no active position)

    All calculations are vectorized using NumPy/Pandas — no Python loops
    over the main data array.

    Args:
        df: DataFrame with columns: Open, High, Low, Close, Volume, Pivot.
            Must be indexed chronologically (oldest first).
        config: Engine hyperparameters. Uses defaults if None.

    Returns:
        The input DataFrame with signal columns appended.

    Raises:
        ValueError: If required columns are missing from the DataFrame.
    """
    if config is None:
        config = EngineConfig()

    _validate_dataframe(df)

    # Step 1: Compute rolling resistance and support zones
    df = _compute_touch_zones(df, config)

    # Step 2: Detect touches at resistance/support
    df = _detect_touches(df, config)

    # Step 3: Accumulate touch counts within lookback window
    df = _accumulate_touches(df, config)

    # Step 4: Detect breakouts with volume confirmation
    df = _detect_breakouts(df, config)

    # Step 5: Compute ATR and apply ratcheting trailing stop
    df = _compute_atr_trailing_stop(df, config)

    return df


def _validate_dataframe(df: pd.DataFrame) -> None:
    """Validate that all required columns exist in the DataFrame.

    Args:
        df: Input DataFrame to validate.

    Raises:
        ValueError: If any required column is missing.
    """
    required_cols = {"Open", "High", "Low", "Close", "Volume", "Pivot"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"DataFrame missing required columns: {missing}. "
            f"Required: {required_cols}"
        )
    if len(df) < 10:
        raise ValueError(
            f"DataFrame has {len(df)} rows, minimum 10 required for analysis."
        )


def _compute_touch_zones(df: pd.DataFrame, config: EngineConfig) -> pd.DataFrame:
    """Compute adaptive resistance and support zones using rolling window.

    Resistance zone: Rolling max high * (1 - tolerance)
    Support zone: Rolling min low * (1 + tolerance)

    These define the "zone" within which a candle is considered to be
    testing a structural level.

    Args:
        df: Input DataFrame with High, Low columns.
        config: Engine configuration with lookback and tolerance.

    Returns:
        DataFrame with added columns: _Rolling_Res, _Rolling_Sup.
    """
    lookback = config.lookback
    tolerance = config.tolerance

    # Vectorized rolling max/min
    df["_Rolling_Res"] = df["High"].rolling(window=lookback, min_periods=1).max()
    df["_Rolling_Sup"] = df["Low"].rolling(window=lookback, min_periods=1).min()

    # Apply tolerance to create zone boundaries
    df["_Res_Zone_Lower"] = df["_Rolling_Res"] * (1 - tolerance)
    df["_Sup_Zone_Upper"] = df["_Rolling_Sup"] * (1 + tolerance)

    return df


def _detect_touches(df: pd.DataFrame, config: EngineConfig) -> pd.DataFrame:
    """Detect resistance and support touches using vectorized comparisons.

    Resistance touch: High >= Rolling_Max_High * (1 - tolerance)
        AND Close < Rolling_Max_High (rejected — didn't break through)

    Support touch: Low <= Rolling_Min_Low * (1 + tolerance)
        AND Close > Rolling_Min_Low (bounced — didn't break through)

    Args:
        df: DataFrame with _Rolling_Res, _Res_Zone_Lower, etc.
        config: Engine configuration.

    Returns:
        DataFrame with Is_Resistance_Touch and Is_Support_Touch columns.
    """
    # Resistance touch: high reaches into the resistance zone but closes below
    df["Is_Resistance_Touch"] = np.where(
        (df["High"] >= df["_Res_Zone_Lower"]) & (df["Close"] < df["_Rolling_Res"]),
        1, 0
    ).astype(np.int8)

    # Support touch: low reaches into the support zone but closes above
    df["Is_Support_Touch"] = np.where(
        (df["Low"] <= df["_Sup_Zone_Upper"]) & (df["Close"] > df["_Rolling_Sup"]),
        1, 0
    ).astype(np.int8)

    return df


def _accumulate_touches(df: pd.DataFrame, config: EngineConfig) -> pd.DataFrame:
    """Count accumulated touches within the lookback window.

    Uses rolling sum over the lookback period to count how many times
    resistance or support has been tested recently.

    The Accumulated_Touches column takes the MAX of resistance touches
    and support touches — whichever side has more activity.

    Args:
        df: DataFrame with Is_Resistance_Touch and Is_Support_Touch.
        config: Engine configuration with lookback window.

    Returns:
        DataFrame with Accumulated_Touches column.
    """
    lookback = config.lookback

    res_acc = df["Is_Resistance_Touch"].rolling(
        window=lookback, min_periods=1
    ).sum()

    sup_acc = df["Is_Support_Touch"].rolling(
        window=lookback, min_periods=1
    ).sum()

    # Take the max of the two sides — we care about whichever level
    # has been tested most frequently
    df["Accumulated_Touches"] = np.maximum(res_acc, sup_acc).astype(int)

    # Also store individual counts for downstream use
    df["_Res_Touches_Acc"] = res_acc.astype(int)
    df["_Sup_Touches_Acc"] = sup_acc.astype(int)

    return df


def _detect_breakouts(df: pd.DataFrame, config: EngineConfig) -> pd.DataFrame:
    """Detect breakout/breakdown signals with volume confirmation.

    Bullish breakout conditions (all must be true):
    1. Close > Rolling_Max_High (price breaks above resistance)
    2. Accumulated resistance touches >= min_touches
    3. Volume > Vol_SMA * vol_multiplier (exhaustion volume)
    4. Compression rule: Low > Low.shift(lookback/2) (ascending lows)

    Bearish breakdown conditions (all must be true):
    1. Close < Rolling_Min_Low (price breaks below support)
    2. Accumulated support touches >= min_touches
    3. Volume > Vol_SMA * vol_multiplier
    4. Compression rule: High < High.shift(lookback/2) (descending highs)

    Args:
        df: DataFrame with touch accumulation and zone columns.
        config: Engine configuration.

    Returns:
        DataFrame with Breakout_Signal column (1, -1, or 0).
    """
    lookback = config.lookback
    vol_mult = config.vol_multiplier
    min_touches = config.min_touches

    # Volume filter: SMA of volume over lookback
    df["_Vol_SMA"] = df["Volume"].rolling(window=lookback, min_periods=1).mean()
    vol_confirmed = df["Volume"] > (df["_Vol_SMA"] * vol_mult)

    # Compression rules
    half_lookback = max(1, lookback // 2)
    ascending_lows = df["Low"] > df["Low"].shift(half_lookback)
    descending_highs = df["High"] < df["High"].shift(half_lookback)

    # Bullish breakout: close breaks above resistance with sufficient touches
    bullish_break = (
        (df["Close"] > df["_Rolling_Res"])
        & (df["_Res_Touches_Acc"] >= min_touches)
        & vol_confirmed
        & ascending_lows
    )

    # Bearish breakdown: close breaks below support with sufficient touches
    bearish_break = (
        (df["Close"] < df["_Rolling_Sup"])
        & (df["_Sup_Touches_Acc"] >= min_touches)
        & vol_confirmed
        & descending_highs
    )

    # Assign signal values: bullish=1, bearish=-1, none=0
    # If both trigger on same candle (unlikely), bullish takes priority
    df["Breakout_Signal"] = np.where(
        bullish_break, SignalDirection.BUY_CALL,
        np.where(bearish_break, SignalDirection.BUY_PUT, SignalDirection.NONE)
    ).astype(np.int8)

    return df


def _compute_atr_trailing_stop(
    df: pd.DataFrame, config: EngineConfig
) -> pd.DataFrame:
    """Compute ATR and apply ratcheting trailing stop-loss logic.

    True Range (TR) = max(High - Low, |High - Close_prev|, |Low - Close_prev|)
    ATR = SMA of TR over atr_period candles.

    Ratcheting logic:
    - Long: stop can only move UP → max(prev_stop, Close - ATR * multiplier)
    - Short: stop can only move DOWN → min(prev_stop, Close + ATR * multiplier)

    The trailing stop is NaN when no position is active (Breakout_Signal == 0).
    Once a signal fires, the stop tracks until the opposite signal or SL breach.

    Note: The ratcheting logic requires sequential state, so we use a single
    pass with NumPy pre-allocated arrays (not a Python-level per-element loop
    on the indicator calculations).

    Args:
        df: DataFrame with Breakout_Signal, High, Low, Close columns.
        config: Engine configuration with atr_period and atr_multiplier.

    Returns:
        DataFrame with ATR and Dynamic_Trailing_SL columns.
    """
    period = config.atr_period
    multiplier = config.atr_multiplier

    # Vectorized True Range calculation
    prev_close = df["Close"].shift(1)
    tr1 = df["High"] - df["Low"]
    tr2 = (df["High"] - prev_close).abs()
    tr3 = (df["Low"] - prev_close).abs()
    df["_TR"] = np.maximum(tr1, np.maximum(tr2, tr3))

    # ATR as SMA of True Range (vectorized)
    df["ATR"] = df["_TR"].rolling(window=period, min_periods=1).mean()

    # Ratcheting trailing stop — requires sequential state propagation
    # Pre-allocate arrays for performance
    n = len(df)
    trailing_sl = np.full(n, np.nan)
    signals = df["Breakout_Signal"].values
    closes = df["Close"].values
    atrs = df["ATR"].values

    # State: current position direction (0=flat, 1=long, -1=short)
    position = 0

    for i in range(n):
        sig = signals[i]
        close_i = closes[i]
        atr_i = atrs[i]

        if sig == SignalDirection.BUY_CALL:
            # New long position — initialize stop below
            position = 1
            trailing_sl[i] = close_i - (atr_i * multiplier)

        elif sig == SignalDirection.BUY_PUT:
            # New short position — initialize stop above
            position = -1
            trailing_sl[i] = close_i + (atr_i * multiplier)

        elif position == 1:
            # Long position: ratchet stop UP only
            new_stop = close_i - (atr_i * multiplier)
            trailing_sl[i] = max(trailing_sl[i - 1], new_stop)
            # Check if stop was breached
            if close_i < trailing_sl[i]:
                position = 0
                trailing_sl[i] = np.nan

        elif position == -1:
            # Short position: ratchet stop DOWN only
            new_stop = close_i + (atr_i * multiplier)
            trailing_sl[i] = min(trailing_sl[i - 1], new_stop)
            # Check if stop was breached
            if close_i > trailing_sl[i]:
                position = 0
                trailing_sl[i] = np.nan

        # else: position == 0, remain flat (NaN)

    df["Dynamic_Trailing_SL"] = trailing_sl

    return df


# --- Trade State Manager ---

@dataclass
class ActiveTrade:
    """Represents an active trade being tracked by the state manager.

    Attributes:
        entry_index: DataFrame row index where the trade was entered.
        direction: 1 for long (call), -1 for short (put).
        entry_price: Price at which the trade was entered.
        entry_atr: ATR value at entry (used for initial stop calculation).
        initial_stop: Initial stop-loss value at entry.
        current_stop: Current trailing stop-loss value (ratchets only).
        peak_price: Highest price seen (long) or lowest (short) since entry.
        is_active: Whether the trade is still open.
        exit_price: Price at which the trade was exited (NaN if active).
        exit_reason: Reason for exit ("stop_loss", "signal_reversal", or "").
    """
    entry_index: int
    direction: int  # 1 = long, -1 = short
    entry_price: float
    entry_atr: float
    initial_stop: float
    current_stop: float
    peak_price: float
    is_active: bool = True
    exit_price: float = float("nan")
    exit_reason: str = ""


class TradeStateManager:
    """Manages active trade positions with ratcheting ATR trailing stops.

    Tracks entry, monitors price progression, updates trailing stop
    on each new candle, and flags exits when stop is breached or
    a reversal signal fires.

    This class is designed to be called candle-by-candle in a live
    trading loop or backtesting engine.

    Usage:
        manager = TradeStateManager(config)
        for each candle:
            result = manager.update(candle_data, breakout_signal)
            if result and result.exit_reason:
                # Handle exit
    """

    def __init__(self, config: Optional[EngineConfig] = None) -> None:
        """Initialize TradeStateManager.

        Args:
            config: Engine configuration. Uses defaults if None.
        """
        self.config = config or EngineConfig()
        self.active_trade: Optional[ActiveTrade] = None
        self.trade_history: List[ActiveTrade] = []
        self._candle_count: int = 0


    @property
    def is_flat(self) -> bool:
        """Whether there is no active position."""
        return self.active_trade is None or not self.active_trade.is_active

    @property
    def current_position(self) -> int:
        """Current position direction: 1, -1, or 0."""
        if self.is_flat:
            return 0
        return self.active_trade.direction

    def update(
        self,
        close: float,
        high: float,
        low: float,
        atr: float,
        signal: int,
        index: int = 0,
    ) -> Optional[ActiveTrade]:
        """Process a new candle and update trade state.

        Call this once per candle with the latest OHLC + ATR + signal.

        Logic:
        1. If a new signal fires and we're flat → open new trade
        2. If a reversal signal fires (opposite direction) → close + open
        3. If active trade, update trailing stop (ratchet only)
        4. If stop breached → close trade, return to flat

        Args:
            close: Current candle close price.
            high: Current candle high price.
            low: Current candle low price.
            atr: Current ATR value.
            signal: Breakout signal (1, -1, or 0).
            index: Current candle index (for tracking).

        Returns:
            The ActiveTrade if a state change occurred (new entry, exit),
            or None if no change.
        """
        self._candle_count += 1
        multiplier = self.config.atr_multiplier

        # --- Handle new signals ---
        if signal == SignalDirection.BUY_CALL:
            return self._enter_trade(
                direction=1,
                entry_price=close,
                atr=atr,
                stop=close - (atr * multiplier),
                index=index,
            )

        elif signal == SignalDirection.BUY_PUT:
            return self._enter_trade(
                direction=-1,
                entry_price=close,
                atr=atr,
                stop=close + (atr * multiplier),
                index=index,
            )

        # --- Update existing position ---
        if self.active_trade and self.active_trade.is_active:
            return self._update_trailing_stop(close, high, low, atr, index)

        return None


    def _enter_trade(
        self,
        direction: int,
        entry_price: float,
        atr: float,
        stop: float,
        index: int,
    ) -> ActiveTrade:
        """Open a new trade, closing any existing position first.

        Args:
            direction: 1 for long, -1 for short.
            entry_price: Entry price.
            atr: ATR at entry.
            stop: Initial stop-loss value.
            index: Candle index.

        Returns:
            The newly created ActiveTrade.
        """
        # Close existing position if any (signal reversal)
        if self.active_trade and self.active_trade.is_active:
            self.active_trade.is_active = False
            self.active_trade.exit_price = entry_price
            self.active_trade.exit_reason = "signal_reversal"
            self.trade_history.append(self.active_trade)

        self.active_trade = ActiveTrade(
            entry_index=index,
            direction=direction,
            entry_price=entry_price,
            entry_atr=atr,
            initial_stop=stop,
            current_stop=stop,
            peak_price=entry_price,
        )

        logger.debug(
            "Entered %s at %.2f, initial SL=%.2f (ATR=%.2f, mult=%.1f)",
            "LONG" if direction == 1 else "SHORT",
            entry_price, stop, atr, self.config.atr_multiplier,
        )

        return self.active_trade

    def _update_trailing_stop(
        self,
        close: float,
        high: float,
        low: float,
        atr: float,
        index: int,
    ) -> Optional[ActiveTrade]:
        """Update the ratcheting trailing stop for the active trade.

        Long: stop = max(prev_stop, close - ATR * multiplier)
        Short: stop = min(prev_stop, close + ATR * multiplier)

        If price breaches the stop, the trade is closed.

        Args:
            close: Current close price.
            high: Current high price.
            low: Current low price.
            atr: Current ATR value.
            index: Current candle index.

        Returns:
            ActiveTrade if the trade was closed (stop breached), else None.
        """
        trade = self.active_trade
        multiplier = self.config.atr_multiplier

        if trade.direction == 1:  # Long position
            # Update peak (for tracking, not used in stop calc)
            trade.peak_price = max(trade.peak_price, high)

            # Ratchet stop UP only
            new_stop = close - (atr * multiplier)
            trade.current_stop = max(trade.current_stop, new_stop)

            # Check if low breached the stop
            if low <= trade.current_stop:
                trade.is_active = False
                trade.exit_price = trade.current_stop  # Assume fill at stop
                trade.exit_reason = "stop_loss"
                self.trade_history.append(trade)
                self.active_trade = None
                logger.debug(
                    "LONG stopped out at %.2f (entry=%.2f)", 
                    trade.exit_price, trade.entry_price,
                )
                return trade

        else:  # Short position
            trade.peak_price = min(trade.peak_price, low)

            # Ratchet stop DOWN only
            new_stop = close + (atr * multiplier)
            trade.current_stop = min(trade.current_stop, new_stop)

            # Check if high breached the stop
            if high >= trade.current_stop:
                trade.is_active = False
                trade.exit_price = trade.current_stop
                trade.exit_reason = "stop_loss"
                self.trade_history.append(trade)
                self.active_trade = None
                logger.debug(
                    "SHORT stopped out at %.2f (entry=%.2f)",
                    trade.exit_price, trade.entry_price,
                )
                return trade

        return None


    def get_trade_summary(self) -> Dict:
        """Get summary statistics for all completed trades.

        Returns:
            Dict with trade statistics:
            - total_trades: Number of completed trades.
            - winning_trades: Trades with positive P&L.
            - losing_trades: Trades with negative P&L.
            - win_rate: Winning percentage.
            - total_pnl: Sum of all trade P&L.
            - avg_pnl: Average P&L per trade.
            - max_win: Largest winning trade.
            - max_loss: Largest losing trade.
        """
        if not self.trade_history:
            return {
                "total_trades": 0, "winning_trades": 0,
                "losing_trades": 0, "win_rate": 0.0,
                "total_pnl": 0.0, "avg_pnl": 0.0,
                "max_win": 0.0, "max_loss": 0.0,
            }

        pnls = []
        for trade in self.trade_history:
            if trade.direction == 1:
                pnl = trade.exit_price - trade.entry_price
            else:
                pnl = trade.entry_price - trade.exit_price
            pnls.append(pnl)

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        return {
            "total_trades": len(pnls),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": round(len(wins) / len(pnls) * 100, 2) if pnls else 0.0,
            "total_pnl": round(sum(pnls), 2),
            "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
            "max_win": round(max(wins), 2) if wins else 0.0,
            "max_loss": round(min(losses), 2) if losses else 0.0,
        }

    def reset(self) -> None:
        """Reset the state manager, clearing all positions and history."""
        self.active_trade = None
        self.trade_history = []
        self._candle_count = 0


# --- Utility Functions ---

def prepare_dataframe(
    candles: List[Dict],
    pivot_value: Optional[float] = None,
) -> pd.DataFrame:
    """Convert raw candle dicts to a DataFrame ready for detect_signals().

    Convenience function to bridge from the existing candle data format
    used by scanner_service.py and pivot_breakout_service.py to the
    DataFrame format expected by this engine.

    Args:
        candles: List of candle dicts with keys:
            open, high, low, close, volume, and optionally timestamp.
        pivot_value: Daily pivot point value. If None, uses midpoint of
            first candle's (high + low + close) / 3.

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume, Pivot.
    """
    df = pd.DataFrame(candles)

    # Normalize column names (handle both lowercase and capitalized)
    col_map = {}
    for col in df.columns:
        lower = col.lower()
        if lower == "open":
            col_map[col] = "Open"
        elif lower == "high":
            col_map[col] = "High"
        elif lower == "low":
            col_map[col] = "Low"
        elif lower == "close":
            col_map[col] = "Close"
        elif lower == "volume":
            col_map[col] = "Volume"
        elif lower == "timestamp" or lower == "date":
            col_map[col] = "Timestamp"

    df = df.rename(columns=col_map)

    # Set Pivot column
    if pivot_value is not None:
        df["Pivot"] = pivot_value
    elif "Pivot" not in df.columns:
        # Default: use typical price of first candle as pivot
        first = df.iloc[0]
        df["Pivot"] = (first["High"] + first["Low"] + first["Close"]) / 3

    # Ensure numeric types
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Fill any NaN volumes with 0
    df["Volume"] = df["Volume"].fillna(0)

    # Set timestamp as index if available
    if "Timestamp" in df.columns:
        df = df.set_index("Timestamp")

    return df


def get_active_signals(df: pd.DataFrame) -> List[BreakoutSignalResult]:
    """Extract all detected breakout signals from a processed DataFrame.

    Filters rows where Breakout_Signal != 0 and returns structured results.

    Args:
        df: DataFrame already processed by detect_signals().

    Returns:
        List of BreakoutSignalResult objects.
    """
    signal_rows = df[df["Breakout_Signal"] != 0]
    results = []

    for idx, row in signal_rows.iterrows():
        direction = int(row["Breakout_Signal"])

        # Determine the level that was broken
        if direction == SignalDirection.BUY_CALL:
            level = row.get("_Rolling_Res", row["Pivot"])
        else:
            level = row.get("_Rolling_Sup", row["Pivot"])

        atr_val = row.get("ATR", 0.0)
        multiplier = DEFAULT_ATR_MULTIPLIER

        if direction == SignalDirection.BUY_CALL:
            initial_sl = row["Close"] - (atr_val * multiplier)
        else:
            initial_sl = row["Close"] + (atr_val * multiplier)

        # Simple confidence: base 60 + touches bonus + volume bonus
        touches = int(row.get("Accumulated_Touches", 0))
        vol_sma = row.get("_Vol_SMA", 1)
        vol_ratio = row["Volume"] / vol_sma if vol_sma > 0 else 1.0

        confidence = min(100, 60 + (touches - 2) * 8 + (vol_ratio - 1) * 10)
        confidence = max(50, confidence)

        results.append(BreakoutSignalResult(
            index=idx if isinstance(idx, int) else signal_rows.index.get_loc(idx),
            direction=direction,
            level_value=round(float(level), 2),
            touch_count=touches,
            breakout_price=round(float(row["Close"]), 2),
            volume_confirmed=vol_ratio >= DEFAULT_VOL_MULTIPLIER,
            atr_value=round(float(atr_val), 2),
            initial_stop_loss=round(float(initial_sl), 2),
            confidence_score=round(confidence, 2),
            timestamp=str(idx) if not isinstance(idx, int) else "",
        ))

    return results


def cleanup_internal_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Remove internal calculation columns, keeping only the output schema.

    Keeps: Open, High, Low, Close, Volume, Pivot, Is_Resistance_Touch,
    Is_Support_Touch, Accumulated_Touches, Breakout_Signal,
    Dynamic_Trailing_SL, ATR.

    Args:
        df: Processed DataFrame from detect_signals().

    Returns:
        DataFrame with only user-facing columns.
    """
    internal_cols = [
        "_Rolling_Res", "_Rolling_Sup", "_Res_Zone_Lower",
        "_Sup_Zone_Upper", "_Vol_SMA", "_TR",
        "_Res_Touches_Acc", "_Sup_Touches_Acc",
    ]
    cols_to_drop = [c for c in internal_cols if c in df.columns]
    return df.drop(columns=cols_to_drop)


# --- Fixed-Level (Pivot Point) Mode ---

def detect_pivot_level_breakouts(
    df: pd.DataFrame,
    levels: Dict[str, float],
    config: Optional[EngineConfig] = None,
) -> pd.DataFrame:
    """Detect multi-touch breakouts at SPECIFIC pivot levels (R1, R2, S1, S2, etc).

    Unlike detect_signals() which uses adaptive rolling zones, this function
    targets pre-calculated pivot levels (from previous day's OHLC).

    For each level, it:
    1. Counts candles that touch the level (within tolerance)
    2. Tracks which candles register as a "touch" (approach + rejection)
    3. Fires a breakout signal when close crosses the level with enough touches
    4. Applies volume confirmation

    This directly replicates the Three-Touch Rule pattern observed in today's
    session where R2 (24,426.37) was touched 3 times before breaking up.

    Args:
        df: DataFrame with Open, High, Low, Close, Volume columns.
        levels: Dict of level names to prices, e.g. {"R2": 24426.37, "S1": 24222.98}.
        config: Engine configuration. Uses defaults if None.

    Returns:
        DataFrame with added columns per level:
        - Touch_{level}: 1 if candle touches this level
        - Touches_Acc_{level}: Accumulated touch count
        - Break_{level}: 1 (upside break), -1 (downside break), 0 (none)
        Plus overall: Breakout_Signal, Dynamic_Trailing_SL, ATR
    """
    if config is None:
        config = EngineConfig()

    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    # Compute volume SMA for confirmation
    df["_Vol_SMA"] = df["Volume"].rolling(window=config.lookback, min_periods=1).mean()

    # Compute ATR
    prev_close = df["Close"].shift(1)
    tr1 = df["High"] - df["Low"]
    tr2 = (df["High"] - prev_close).abs()
    tr3 = (df["Low"] - prev_close).abs()
    df["_TR"] = np.maximum(tr1, np.maximum(tr2, tr3))
    df["ATR"] = df["_TR"].rolling(window=config.atr_period, min_periods=1).mean()

    # Initialize overall signal column
    df["Breakout_Signal"] = 0

    for level_name, level_value in levels.items():
        tolerance = level_value * config.tolerance
        touch_col = f"Touch_{level_name}"
        acc_col = f"Touches_Acc_{level_name}"
        break_col = f"Break_{level_name}"

        # Detect touches: high reaches within tolerance of resistance level
        # AND close stays below (rejection)
        is_resistance_touch = (
            (df["High"] >= level_value - tolerance)
            & (df["High"] <= level_value + tolerance)
            & (df["Close"] < level_value)
        )

        # OR: low reaches within tolerance of support level
        # AND close stays above (bounce)
        is_support_touch = (
            (df["Low"] >= level_value - tolerance)
            & (df["Low"] <= level_value + tolerance)
            & (df["Close"] > level_value)
        )

        df[touch_col] = np.where(
            is_resistance_touch | is_support_touch, 1, 0
        ).astype(np.int8)

        # Accumulate touches over lookback
        df[acc_col] = df[touch_col].rolling(
            window=config.lookback, min_periods=1
        ).sum().astype(int)

        # Detect breakout: close crosses level with enough accumulated touches
        # Upside: close > level AND accumulated touches >= min_touches
        vol_ok = df["Volume"] > (df["_Vol_SMA"] * config.vol_multiplier)

        upside_break = (
            (df["Close"] > level_value + tolerance)
            & (df[acc_col] >= config.min_touches)
            & vol_ok
        )

        # Downside: close < level AND accumulated touches >= min_touches
        downside_break = (
            (df["Close"] < level_value - tolerance)
            & (df[acc_col] >= config.min_touches)
            & vol_ok
        )

        df[break_col] = np.where(
            upside_break, 1,
            np.where(downside_break, -1, 0)
        ).astype(np.int8)

        # Merge into overall signal (first signal wins per candle)
        df["Breakout_Signal"] = np.where(
            (df["Breakout_Signal"] == 0) & (df[break_col] != 0),
            df[break_col],
            df["Breakout_Signal"],
        )

    # Apply ratcheting trailing stop to breakout signals
    df = _compute_atr_trailing_stop(df, config)

    return df
