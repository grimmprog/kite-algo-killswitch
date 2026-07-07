"""
Trend Engine for generating trend-following entry and exit signals.
"""

from typing import Optional
from datetime import datetime

from ..data.candle_builder import CandleBuilder
from ..data.indicator_service import IndicatorService
from ..analysis.market_state_detector import MarketStateDetector
from ..execution.models import Signal
from ..common.enums import TrendState, SignalType
from ..config import TrendConfig


class TrendBook:
    """
    Logical position book for trend-following trades.
    
    Tracks the current trend position, average entry price, and trade history.
    """
    
    def __init__(self):
        """Initialize empty trend book."""
        self.position = 0  # Current net position (positive = long, negative = short)
        self.avg_entry_price = 0.0
        self.trades = []  # List of trend trades
    
    def add_position(self, quantity: int, price: float):
        """
        Add to position (positive for long, negative for short).
        
        Args:
            quantity: Quantity to add (positive for long, negative for short)
            price: Entry price
        """
        if self.position == 0:
            self.avg_entry_price = price
        else:
            # Update average entry price
            total_value = self.position * self.avg_entry_price + quantity * price
            self.position += quantity
            self.avg_entry_price = total_value / self.position if self.position != 0 else 0.0
        
        self.position += quantity if self.position == 0 else 0
    
    def reduce_position(self, quantity: int, price: float):
        """
        Reduce position (FIFO accounting).
        
        Args:
            quantity: Quantity to reduce (always positive)
            price: Exit price
        """
        if quantity > abs(self.position):
            raise ValueError(f"Cannot reduce position by {quantity}, current position is {self.position}")
        
        # Reduce position
        if self.position > 0:
            self.position -= quantity
        else:
            self.position += quantity
        
        # Reset average price if position is zero
        if self.position == 0:
            self.avg_entry_price = 0.0


class TrendEngine:
    """
    Trend-following engine that generates entry and exit signals based on structure.
    
    Entry Logic:
    - Long: UPTREND + pullback to structure (HL or EMA zone) + not at vertical extension
    - Short: DOWNTREND + pullback to structure (LH or EMA zone) + not at vertical extension
    
    Exit Logic:
    - Full exit: Structure break OR opposite trend confirmed
    - Partial exit: Trend weakening detected
    """
    
    def __init__(self, market_state: MarketStateDetector, 
                 indicator_service: IndicatorService,
                 config: TrendConfig):
        """
        Initialize Trend Engine.
        
        Args:
            market_state: MarketStateDetector instance
            indicator_service: IndicatorService instance
            config: TrendConfig with engine parameters
        """
        self.market_state = market_state
        self.indicator_service = indicator_service
        self.config = config
        self.timeframe = config.timeframe
    
    def evaluate(self, trend_book: TrendBook, current_price: float) -> Optional[Signal]:
        """
        Evaluate trend conditions and generate signals.
        
        Args:
            trend_book: TrendBook instance with current position
            current_price: Current market price
        
        Returns:
            Signal object or None if no signal generated
        """
        # Detect current trend state
        trend_state = self.market_state.detect_trend_state(self.timeframe)
        
        # Check for exit conditions first (if we have a position)
        if trend_book.position != 0:
            exit_signal = self.check_exit_conditions(trend_state, trend_book, current_price)
            if exit_signal:
                return exit_signal
        
        # Check for entry conditions (if we don't have a position)
        if trend_book.position == 0:
            entry_signal = self.check_entry_conditions(trend_state, trend_book, current_price)
            if entry_signal:
                return entry_signal
        
        return None
    
    def check_entry_conditions(self, trend_state: TrendState, 
                               trend_book: TrendBook,
                               current_price: float) -> Optional[Signal]:
        """
        Check if entry conditions are met for trend-following trades.
        
        Entry conditions:
        - UPTREND: Price pulls back to structure (HL or EMA zone) AND not at vertical extension
        - DOWNTREND: Price pulls back to structure (LH or EMA zone) AND not at vertical extension
        
        Args:
            trend_state: Current trend state
            trend_book: TrendBook instance
            current_price: Current market price
        
        Returns:
            Signal object or None
        """
        # Only enter if no existing position
        if trend_book.position != 0:
            return None
        
        # Check for vertical extension (reject if true)
        if self.market_state.is_vertical_extension(
            self.timeframe,
            body_threshold=self.config.vertical_extension_body_threshold,
            distance_threshold=self.config.vertical_extension_distance_threshold
        ):
            return None
        
        # Calculate ATR for structure proximity check
        atr = self.indicator_service.calculate_atr(self.timeframe, period=self.config.ema_period)
        if atr is None or atr == 0:
            return None
        
        # Calculate EMA as structural reference
        ema_20 = self.indicator_service.calculate_ema(self.timeframe, period=self.config.ema_period)
        if ema_20 is None:
            return None
        
        # UPTREND entry logic
        if trend_state == TrendState.UPTREND:
            # Find previous higher low (structure level)
            structure_level = self.market_state.find_structure_level(self.timeframe, direction='up')
            
            # Check if price is near structure or EMA zone
            near_structure = False
            if structure_level is not None:
                distance_to_structure = abs(current_price - structure_level)
                near_structure = distance_to_structure < self.config.structure_proximity_atr_multiplier * atr
            
            distance_to_ema = abs(current_price - ema_20)
            near_ema = distance_to_ema < self.config.structure_proximity_atr_multiplier * atr
            
            if near_structure or near_ema:
                return Signal(
                    signal_type=SignalType.ENTRY_LONG,
                    engine='trend',
                    quantity=self.config.base_position_size,
                    reason=f'Pullback to structure in uptrend (near_structure={near_structure}, near_ema={near_ema})',
                    timestamp=datetime.now(),
                    price=current_price
                )
        
        # DOWNTREND entry logic
        elif trend_state == TrendState.DOWNTREND:
            # Find previous lower high (structure level)
            structure_level = self.market_state.find_structure_level(self.timeframe, direction='down')
            
            # Check if price is near structure or EMA zone
            near_structure = False
            if structure_level is not None:
                distance_to_structure = abs(current_price - structure_level)
                near_structure = distance_to_structure < self.config.structure_proximity_atr_multiplier * atr
            
            distance_to_ema = abs(current_price - ema_20)
            near_ema = distance_to_ema < self.config.structure_proximity_atr_multiplier * atr
            
            if near_structure or near_ema:
                return Signal(
                    signal_type=SignalType.ENTRY_SHORT,
                    engine='trend',
                    quantity=self.config.base_position_size,
                    reason=f'Pullback to structure in downtrend (near_structure={near_structure}, near_ema={near_ema})',
                    timestamp=datetime.now(),
                    price=current_price
                )
        
        return None
    
    def check_exit_conditions(self, trend_state: TrendState,
                              trend_book: TrendBook,
                              current_price: float) -> Optional[Signal]:
        """
        Check if exit conditions are met for trend-following trades.
        
        Exit conditions:
        - Full exit: Structure break OR opposite trend confirmed
        - Partial exit: Trend weakening detected
        
        Args:
            trend_state: Current trend state
            trend_book: TrendBook instance
            current_price: Current market price
        
        Returns:
            Signal object or None
        """
        if trend_book.position == 0:
            return None
        
        # Determine position direction
        is_long = trend_book.position > 0
        direction = 'up' if is_long else 'down'
        
        # Check for structure break (full exit)
        if self.market_state.detect_structure_break(self.timeframe):
            return Signal(
                signal_type=SignalType.EXIT_FULL,
                engine='trend',
                quantity=abs(trend_book.position),
                reason='Structure break detected',
                timestamp=datetime.now(),
                price=current_price
            )
        
        # Check for opposite trend confirmation (full exit)
        if is_long and trend_state == TrendState.DOWNTREND:
            # Confirm opposite trend with 2 consecutive closes beyond structure
            if self._is_opposite_trend_confirmed(trend_state):
                return Signal(
                    signal_type=SignalType.EXIT_FULL,
                    engine='trend',
                    quantity=abs(trend_book.position),
                    reason='Opposite trend confirmed (downtrend after long position)',
                    timestamp=datetime.now(),
                    price=current_price
                )
        
        elif not is_long and trend_state == TrendState.UPTREND:
            # Confirm opposite trend with 2 consecutive closes beyond structure
            if self._is_opposite_trend_confirmed(trend_state):
                return Signal(
                    signal_type=SignalType.EXIT_FULL,
                    engine='trend',
                    quantity=abs(trend_book.position),
                    reason='Opposite trend confirmed (uptrend after short position)',
                    timestamp=datetime.now(),
                    price=current_price
                )
        
        # Check for trend weakening (partial exit)
        if self.market_state.detect_trend_weakening(
            self.timeframe,
            direction=direction,
            failure_candles=self.config.trend_weakening_candles,
            reduced_range_count=self.config.trend_weakening_reduced_range_count
        ):
            # Calculate partial exit quantity
            partial_qty = int(abs(trend_book.position) * self.config.partial_exit_percentage)
            
            # Ensure at least 1 unit is exited
            if partial_qty == 0:
                partial_qty = 1
            
            return Signal(
                signal_type=SignalType.EXIT_PARTIAL,
                engine='trend',
                quantity=partial_qty,
                reason=f'Trend weakening detected (partial exit {self.config.partial_exit_percentage * 100:.0f}%)',
                timestamp=datetime.now(),
                price=current_price
            )
        
        return None
    
    def _is_opposite_trend_confirmed(self, trend_state: TrendState) -> bool:
        """
        Check if opposite trend is confirmed with 2 consecutive closes beyond structure.
        
        Args:
            trend_state: Current trend state
        
        Returns:
            True if opposite trend confirmed, False otherwise
        """
        # Get recent candles
        candles = self.market_state.candle_builder.get_candles(self.timeframe, 10)
        
        if len(candles) < 3:
            return False
        
        # Get last 2 candles
        last_two = candles[-2:]
        
        # For uptrend confirmation, check if both closes are above previous structure
        if trend_state == TrendState.UPTREND:
            # Find previous lower high (structure to break)
            structure_level = self.market_state.find_structure_level(self.timeframe, direction='down')
            
            if structure_level is None:
                return False
            
            # Check if both closes are above structure
            return all(c.close > structure_level for c in last_two)
        
        # For downtrend confirmation, check if both closes are below previous structure
        elif trend_state == TrendState.DOWNTREND:
            # Find previous higher low (structure to break)
            structure_level = self.market_state.find_structure_level(self.timeframe, direction='up')
            
            if structure_level is None:
                return False
            
            # Check if both closes are below structure
            return all(c.close < structure_level for c in last_two)
        
        return False
