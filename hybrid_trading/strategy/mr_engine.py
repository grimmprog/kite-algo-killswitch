"""
Mean Reversion Engine for generating counter-trend signals during extended moves.

The MR Engine trades counter to the trend direction when the market becomes extended,
providing risk management and drawdown reduction. It only operates when a trend position exists.
"""

from typing import Optional, List
from datetime import datetime

from ..data.candle_builder import CandleBuilder
from ..data.indicator_service import IndicatorService
from ..analysis.market_state_detector import MarketStateDetector
from ..execution.models import Signal, MRTrade
from ..common.enums import TrendState, MRState, SignalType
from ..config import MRConfig
from .trend_engine import TrendBook


class MRBook:
    """
    Logical position book for mean reversion trades.
    
    Tracks active MR trades with their entry details and retracement progress.
    """
    
    def __init__(self):
        """Initialize empty MR book."""
        self.position = 0  # Current net MR position
        self.active_trades = []  # List of active MR trades
    
    def add_trade(self, trade: MRTrade):
        """
        Add a new MR trade.
        
        Args:
            trade: MRTrade instance to add
        """
        self.active_trades.append(trade)
        # Update net position
        if trade.direction == 'long':
            self.position += trade.quantity
        else:
            self.position -= trade.quantity
    
    def close_trade(self, trade: MRTrade, exit_price: float):
        """
        Close an MR trade.
        
        Args:
            trade: MRTrade instance to close
            exit_price: Exit price for the trade
        """
        if trade not in self.active_trades:
            raise ValueError(f"Trade not found in active trades: {trade}")
        
        self.active_trades.remove(trade)
        
        # Update net position
        if trade.direction == 'long':
            self.position -= trade.quantity
        else:
            self.position += trade.quantity


class MeanReversionEngine:
    """
    Mean reversion engine that generates counter-trend signals during extended moves.
    
    Entry Logic:
    - Only enters when trend position exists
    - Enters counter to trend when market is extended (EXTENDED_UP or EXTENDED_DOWN)
    - Position size: max 30% of trend position
    - Ensures net position doesn't flip against trend
    
    Exit Logic:
    - Retracement target: 40-60% of impulse OR structure/EMA touch
    - Time stop: 5 candles (configurable)
    - Momentum loss: Large candle against MR position
    - End of day: Exit all MR trades
    """
    
    def __init__(self, market_state: MarketStateDetector,
                 indicator_service: IndicatorService,
                 config: MRConfig):
        """
        Initialize Mean Reversion Engine.
        
        Args:
            market_state: MarketStateDetector instance
            indicator_service: IndicatorService instance
            config: MRConfig with engine parameters
        """
        self.market_state = market_state
        self.indicator_service = indicator_service
        self.config = config
        self.timeframe = config.timeframe
    
    def evaluate(self, trend_state: TrendState, trend_book: TrendBook,
                 mr_book: MRBook, current_price: float) -> List[Signal]:
        """
        Evaluate MR conditions and generate signals.
        
        Args:
            trend_state: Current trend state
            trend_book: TrendBook instance
            mr_book: MRBook instance
            current_price: Current market price
        
        Returns:
            List of signals (can be multiple exits)
        """
        signals = []
        
        # Check exit conditions for all active MR trades first
        for trade in mr_book.active_trades[:]:  # Use slice to avoid modification during iteration
            exit_signal = self.check_exit_conditions(trade, current_price)
            if exit_signal:
                signals.append(exit_signal)
        
        # Check entry conditions (only if we have room for more trades)
        if len(mr_book.active_trades) < self.config.max_mr_trades_per_leg:
            entry_signal = self.check_entry_conditions(
                trend_state, trend_book, mr_book, current_price
            )
            if entry_signal:
                signals.append(entry_signal)
        
        return signals
    
    def check_entry_conditions(self, trend_state: TrendState, trend_book: TrendBook,
                               mr_book: MRBook, current_price: float) -> Optional[Signal]:
        """
        Check if MR entry conditions are met.
        
        Entry conditions:
        - Trend position must exist (reject if zero)
        - MR state must be extended in trend direction
        - MR position size: max 30% of trend position
        - Net position must not flip against trend
        
        Args:
            trend_state: Current trend state
            trend_book: TrendBook instance
            mr_book: MRBook instance
            current_price: Current market price
        
        Returns:
            Signal object or None
        """
        # MR only trades when trend position exists
        if trend_book.position == 0:
            return None
        
        # Detect MR state
        mr_state = self.market_state.detect_mr_state(self.timeframe)
        
        # UPTREND + EXTENDED_UP -> Short MR position
        if trend_state == TrendState.UPTREND and mr_state == MRState.EXTENDED_UP:
            # Verify net position won't flip BEFORE calculating size
            # For uptrend (long), net position must remain positive after MR short entry
            current_net = trend_book.position + mr_book.position
            
            # Calculate MR position size (max 30% of trend position)
            max_mr_size = int(abs(trend_book.position) * 0.3)
            mr_size = min(self.config.mr_base_size, max_mr_size)
            
            # Ensure at least 1 unit
            if mr_size == 0:
                mr_size = 1
            
            # Check if this size would flip the net position
            net_after_entry = current_net - mr_size
            if net_after_entry <= 0:  # Would flip or neutralize
                return None
            
            # Calculate impulse range for retracement tracking
            impulse_start, impulse_end = self._calculate_impulse_range(current_price)
            
            return Signal(
                signal_type=SignalType.ENTRY_SHORT,
                engine='mr',
                quantity=mr_size,
                reason=f'Extended up in uptrend - MR short (impulse: {impulse_start:.2f} -> {impulse_end:.2f})',
                timestamp=datetime.now(),
                price=current_price
            )
        
        # DOWNTREND + EXTENDED_DOWN -> Long MR position
        elif trend_state == TrendState.DOWNTREND and mr_state == MRState.EXTENDED_DOWN:
            # Verify net position won't flip BEFORE calculating size
            # For downtrend (short), net position must remain negative after MR long entry
            current_net = trend_book.position + mr_book.position
            
            # Calculate MR position size (max 30% of trend position)
            max_mr_size = int(abs(trend_book.position) * 0.3)
            mr_size = min(self.config.mr_base_size, max_mr_size)
            
            # Ensure at least 1 unit
            if mr_size == 0:
                mr_size = 1
            
            # Check if this size would flip the net position
            net_after_entry = current_net + mr_size
            if net_after_entry >= 0:  # Would flip or neutralize
                return None
            
            # Calculate impulse range for retracement tracking
            impulse_start, impulse_end = self._calculate_impulse_range(current_price)
            
            return Signal(
                signal_type=SignalType.ENTRY_LONG,
                engine='mr',
                quantity=mr_size,
                reason=f'Extended down in downtrend - MR long (impulse: {impulse_start:.2f} -> {impulse_end:.2f})',
                timestamp=datetime.now(),
                price=current_price
            )
        
        return None
    
    def check_exit_conditions(self, trade: MRTrade, current_price: float) -> Optional[Signal]:
        """
        Check if exit conditions are met for a specific MR trade.
        
        Exit conditions:
        - Retracement target: 40-60% of impulse OR structure/EMA touch
        - Time stop: 5 candles (configurable)
        - Momentum loss: Large candle against MR position
        
        Args:
            trade: MRTrade instance
            current_price: Current market price
        
        Returns:
            Signal object or None
        """
        # Exit condition 1: Retracement target hit (40-60%) OR touch of structure/EMA
        retracement = trade.retracement_pct(current_price)
        
        # Calculate ATR for structure proximity check
        atr = self.indicator_service.calculate_atr(self.timeframe, period=14)
        if atr is None or atr == 0:
            atr = abs(trade.impulse_end - trade.impulse_start) * 0.1  # Fallback: 10% of impulse
        
        # Find nearest structure level
        structure_level = self._find_nearest_structure_level(current_price)
        structure_touched = False
        if structure_level is not None:
            distance_to_structure = abs(current_price - structure_level)
            structure_touched = distance_to_structure < 0.3 * atr
        
        # Calculate EMA
        ema_20 = self.indicator_service.calculate_ema(self.timeframe, period=20)
        ema_touched = False
        if ema_20 is not None:
            distance_to_ema = abs(current_price - ema_20)
            ema_touched = distance_to_ema < 0.3 * atr
        
        # Check if retracement target hit OR structure/EMA touched
        retracement_hit = self.config.retracement_target_min <= retracement <= self.config.retracement_target_max
        
        if retracement_hit or structure_touched or ema_touched:
            return Signal(
                signal_type=SignalType.EXIT_FULL,
                engine='mr',
                quantity=trade.quantity,
                reason=f'Exit: retracement={retracement:.1f}%, structure_touch={structure_touched}, ema_touch={ema_touched}',
                timestamp=datetime.now(),
                price=current_price
            )
        
        # Exit condition 2: Time stop (e.g., 5 candles)
        if trade.candles_held >= self.config.time_stop_candles:
            return Signal(
                signal_type=SignalType.EXIT_FULL,
                engine='mr',
                quantity=trade.quantity,
                reason=f'Time stop hit: {trade.candles_held} candles',
                timestamp=datetime.now(),
                price=current_price
            )
        
        # Exit condition 3: Momentum loss candle
        if self._detect_momentum_loss_candle(trade):
            return Signal(
                signal_type=SignalType.EXIT_FULL,
                engine='mr',
                quantity=trade.quantity,
                reason='Momentum loss detected',
                timestamp=datetime.now(),
                price=current_price
            )
        
        return None
    
    def exit_all_mr_trades(self, mr_book: MRBook, current_price: float) -> List[Signal]:
        """
        Generate exit signals for all active MR trades (end-of-day logic).
        
        Args:
            mr_book: MRBook instance
            current_price: Current market price
        
        Returns:
            List of exit signals for all active trades
        """
        signals = []
        
        for trade in mr_book.active_trades:
            signal = Signal(
                signal_type=SignalType.EXIT_FULL,
                engine='mr',
                quantity=trade.quantity,
                reason='End-of-day exit for all MR trades',
                timestamp=datetime.now(),
                price=current_price
            )
            signals.append(signal)
        
        return signals
    
    def _calculate_impulse_range(self, current_price: float) -> tuple[float, float]:
        """
        Calculate the impulse start and end prices for retracement tracking.
        
        Args:
            current_price: Current market price
        
        Returns:
            Tuple of (impulse_start, impulse_end)
        """
        # Get recent candles to identify impulse
        candles = self.market_state.candle_builder.get_candles(self.timeframe, 10)
        
        if len(candles) < 3:
            # Fallback: use current price as both start and end
            return (current_price, current_price)
        
        # Find the start of the impulse (look back for swing point)
        # For extended up: find recent swing low
        # For extended down: find recent swing high
        
        # Simple approach: use the low/high of the last 5 candles
        recent_candles = candles[-5:]
        
        # Determine direction based on recent price action
        if current_price > candles[-5].close:
            # Upward impulse: start is recent low, end is current price
            impulse_start = min(c.low for c in recent_candles)
            impulse_end = current_price
        else:
            # Downward impulse: start is recent high, end is current price
            impulse_start = max(c.high for c in recent_candles)
            impulse_end = current_price
        
        return (impulse_start, impulse_end)
    
    def _find_nearest_structure_level(self, current_price: float) -> Optional[float]:
        """
        Find the nearest structure level (swing high or low).
        
        Args:
            current_price: Current market price
        
        Returns:
            Structure level price or None
        """
        # Get recent candles
        candles = self.market_state.candle_builder.get_candles(self.timeframe, 20)
        
        if len(candles) < 5:
            return None
        
        # Find swing highs and lows
        swing_highs = []
        swing_lows = []
        
        for i in range(2, len(candles) - 2):
            # Swing high: higher than 2 candles on each side
            if (candles[i].high > candles[i-1].high and 
                candles[i].high > candles[i-2].high and
                candles[i].high > candles[i+1].high and 
                candles[i].high > candles[i+2].high):
                swing_highs.append(candles[i].high)
            
            # Swing low: lower than 2 candles on each side
            if (candles[i].low < candles[i-1].low and 
                candles[i].low < candles[i-2].low and
                candles[i].low < candles[i+1].low and 
                candles[i].low < candles[i+2].low):
                swing_lows.append(candles[i].low)
        
        # Find nearest structure level
        all_levels = swing_highs + swing_lows
        if not all_levels:
            return None
        
        # Return the level closest to current price
        nearest = min(all_levels, key=lambda x: abs(x - current_price))
        return nearest
    
    def _detect_momentum_loss_candle(self, trade: MRTrade) -> bool:
        """
        Detect if a momentum loss candle appeared against the MR position.
        
        A momentum loss candle is a large candle in the opposite direction of the MR trade
        that suggests the impulse is resuming.
        
        Args:
            trade: MRTrade instance
        
        Returns:
            True if momentum loss detected, False otherwise
        """
        # Get last candle
        candles = self.market_state.candle_builder.get_candles(self.timeframe, 5)
        
        if len(candles) < 2:
            return False
        
        last_candle = candles[-1]
        
        # Calculate average candle body size
        avg_body_size = sum(c.body_size for c in candles) / len(candles)
        
        # Momentum loss for long MR trade: large bearish candle
        if trade.direction == 'long':
            if last_candle.is_bearish and last_candle.body_size > 1.5 * avg_body_size:
                return True
        
        # Momentum loss for short MR trade: large bullish candle
        elif trade.direction == 'short':
            if last_candle.is_bullish and last_candle.body_size > 1.5 * avg_body_size:
                return True
        
        return False
