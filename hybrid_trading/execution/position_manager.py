"""
Position Manager for the Hybrid Trading System.

Maintains separate logical position books (TrendBook and MRBook) while managing
net position reconciliation with the broker.
"""

import logging
from datetime import datetime
from typing import List, Optional

from .models import Trade, MRTrade, Signal
from ..common.enums import SignalType


logger = logging.getLogger(__name__)


class TrendBook:
    """
    Logical position book for trend-following trades.
    
    Tracks the net trend position, average entry price, and trade history.
    """
    
    def __init__(self):
        """Initialize an empty TrendBook."""
        self.position = 0  # Current net position (positive = long, negative = short)
        self.avg_entry_price = 0.0
        self.trades: List[Trade] = []
    
    def add_position(self, quantity: int, price: float):
        """
        Add to the trend position.
        
        Args:
            quantity: Quantity to add (positive for long, negative for short)
            price: Entry price
        """
        if quantity == 0:
            raise ValueError("Cannot add zero quantity")
        if price <= 0:
            raise ValueError(f"Invalid price: {price}")
        
        # Update average entry price
        if self.position == 0:
            # Starting fresh position
            self.avg_entry_price = price
        elif (self.position > 0 and quantity > 0) or (self.position < 0 and quantity < 0):
            # Adding to existing position in same direction
            total_value = abs(self.position) * self.avg_entry_price + abs(quantity) * price
            new_position = self.position + quantity
            self.avg_entry_price = total_value / abs(new_position) if new_position != 0 else 0.0
        else:
            # Reducing position or flipping direction
            # Keep the original avg_entry_price for the remaining position
            # If flipping, set new avg_entry_price
            new_position = self.position + quantity
            if (self.position > 0 and new_position < 0) or (self.position < 0 and new_position > 0):
                # Position flipped direction
                self.avg_entry_price = price
        
        self.position += quantity
        
        # Record trade
        trade = Trade(
            timestamp=datetime.now(),
            quantity=quantity,
            price=price,
            trade_type='trend'
        )
        self.trades.append(trade)
        
        logger.info(f"TrendBook: Added position {quantity} @ {price:.2f}. "
                   f"New position: {self.position}, Avg price: {self.avg_entry_price:.2f}")
    
    def reduce_position(self, quantity: int, price: float):
        """
        Reduce the trend position (exit).
        
        Args:
            quantity: Quantity to reduce (always positive)
            price: Exit price
        """
        if quantity <= 0:
            raise ValueError(f"Quantity must be positive: {quantity}")
        if price <= 0:
            raise ValueError(f"Invalid price: {price}")
        if abs(self.position) < quantity:
            raise ValueError(f"Cannot reduce by {quantity}, current position is {self.position}")
        
        # Determine the direction of reduction
        if self.position > 0:
            # Reducing long position
            reduction = -quantity
        else:
            # Reducing short position
            reduction = quantity
        
        self.position += reduction
        
        # If position is now zero, reset avg_entry_price
        if self.position == 0:
            self.avg_entry_price = 0.0
        
        # Record trade
        trade = Trade(
            timestamp=datetime.now(),
            quantity=reduction,
            price=price,
            trade_type='trend'
        )
        self.trades.append(trade)
        
        logger.info(f"TrendBook: Reduced position by {quantity} @ {price:.2f}. "
                   f"New position: {self.position}, Avg price: {self.avg_entry_price:.2f}")
    
    def get_unrealized_pnl(self, current_price: float) -> float:
        """
        Calculate unrealized P&L for the current position.
        
        Args:
            current_price: Current market price
            
        Returns:
            Unrealized P&L
        """
        if self.position == 0:
            return 0.0
        
        if current_price <= 0:
            raise ValueError(f"Invalid current_price: {current_price}")
        
        if self.position > 0:
            # Long position
            return self.position * (current_price - self.avg_entry_price)
        else:
            # Short position
            return abs(self.position) * (self.avg_entry_price - current_price)
    
    def __repr__(self) -> str:
        """String representation of TrendBook."""
        return (f"TrendBook(position={self.position}, "
                f"avg_entry_price={self.avg_entry_price:.2f}, "
                f"trades={len(self.trades)})")


class MRBook:
    """
    Logical position book for mean reversion trades.
    
    Tracks active MR trades individually with their entry details and holding time.
    """
    
    def __init__(self):
        """Initialize an empty MRBook."""
        self.position = 0  # Current net MR position
        self.active_trades: List[MRTrade] = []
    
    def add_trade(self, trade: MRTrade):
        """
        Add a new mean reversion trade.
        
        Args:
            trade: MRTrade object with entry details
        """
        if not isinstance(trade, MRTrade):
            raise TypeError(f"Expected MRTrade, got {type(trade)}")
        
        self.active_trades.append(trade)
        
        # Update net position
        if trade.direction == 'long':
            self.position += trade.quantity
        else:
            self.position -= trade.quantity
        
        logger.info(f"MRBook: Added {trade.direction} trade {trade.quantity} @ {trade.entry_price:.2f}. "
                   f"New position: {self.position}, Active trades: {len(self.active_trades)}")
    
    def close_trade(self, trade: MRTrade, exit_price: float):
        """
        Close a mean reversion trade.
        
        Args:
            trade: MRTrade object to close
            exit_price: Exit price
        """
        if trade not in self.active_trades:
            raise ValueError("Trade not found in active trades")
        if exit_price <= 0:
            raise ValueError(f"Invalid exit_price: {exit_price}")
        
        self.active_trades.remove(trade)
        
        # Update net position
        if trade.direction == 'long':
            self.position -= trade.quantity
        else:
            self.position += trade.quantity
        
        # Calculate P&L for this trade
        if trade.direction == 'long':
            pnl = trade.quantity * (exit_price - trade.entry_price)
        else:
            pnl = trade.quantity * (trade.entry_price - exit_price)
        
        logger.info(f"MRBook: Closed {trade.direction} trade {trade.quantity} @ {exit_price:.2f}. "
                   f"P&L: {pnl:.2f}, New position: {self.position}, "
                   f"Active trades: {len(self.active_trades)}")
    
    def get_unrealized_pnl(self, current_price: float) -> float:
        """
        Calculate total unrealized P&L for all active MR trades.
        
        Args:
            current_price: Current market price
            
        Returns:
            Total unrealized P&L
        """
        if current_price <= 0:
            raise ValueError(f"Invalid current_price: {current_price}")
        
        total_pnl = 0.0
        for trade in self.active_trades:
            if trade.direction == 'long':
                pnl = trade.quantity * (current_price - trade.entry_price)
            else:
                pnl = trade.quantity * (trade.entry_price - current_price)
            total_pnl += pnl
        
        return total_pnl
    
    def __repr__(self) -> str:
        """String representation of MRBook."""
        return (f"MRBook(position={self.position}, "
                f"active_trades={len(self.active_trades)})")


class PositionManager:
    """
    Manages logical position books and net position reconciliation.
    
    Maintains separate TrendBook and MRBook while ensuring net position
    constraints are respected and broker positions are reconciled.
    """
    
    def __init__(self, order_executor=None):
        """
        Initialize PositionManager.
        
        Args:
            order_executor: OrderExecutor instance for broker queries (optional)
        """
        self.trend_book = TrendBook()
        self.mr_book = MRBook()
        self.order_executor = order_executor
    
    def get_net_position(self) -> int:
        """
        Calculate net position across both books.
        
        Returns:
            Net position (sum of trend and MR positions)
        """
        return self.trend_book.position + self.mr_book.position
    
    def can_enter_mr_position(self, signal: Signal, max_net_position: int = 100) -> bool:
        """
        Check if MR entry would violate position constraints.
        
        Args:
            signal: MR entry signal to validate
            max_net_position: Maximum allowed net position
            
        Returns:
            True if MR entry is allowed, False otherwise
        """
        if signal.engine != 'mr':
            raise ValueError(f"Expected MR signal, got {signal.engine}")
        
        if not signal.signal_type.is_entry:
            raise ValueError(f"Expected entry signal, got {signal.signal_type}")
        
        # Check 1: Trend position must exist
        if self.trend_book.position == 0:
            logger.warning("MR entry rejected: No trend position exists")
            return False
        
        # Check 2: MR position size must be <= 30% of trend position
        max_mr_size = int(abs(self.trend_book.position) * 0.3)
        if signal.quantity > max_mr_size:
            logger.warning(f"MR entry rejected: Quantity {signal.quantity} exceeds "
                          f"max MR size {max_mr_size} (30% of trend position)")
            return False
        
        # Check 3: Net position must not flip against trend
        current_net = self.get_net_position()
        
        if signal.signal_type == SignalType.ENTRY_SHORT:
            net_after = current_net - signal.quantity
            # If trend is long (positive), net must remain positive
            if self.trend_book.position > 0 and net_after <= 0:
                logger.warning(f"MR entry rejected: Would flip net position from {current_net} to {net_after}")
                return False
        
        elif signal.signal_type == SignalType.ENTRY_LONG:
            net_after = current_net + signal.quantity
            # If trend is short (negative), net must remain negative
            if self.trend_book.position < 0 and net_after >= 0:
                logger.warning(f"MR entry rejected: Would flip net position from {current_net} to {net_after}")
                return False
        
        # Check 4: Max net position limit
        if signal.signal_type == SignalType.ENTRY_LONG:
            net_after = current_net + signal.quantity
        else:
            net_after = current_net - signal.quantity
        
        if abs(net_after) > max_net_position:
            logger.warning(f"MR entry rejected: Net position {net_after} would exceed "
                          f"max limit {max_net_position}")
            return False
        
        return True
    
    def reconcile_position(self, symbol: str = None) -> bool:
        """
        Reconcile expected net position with broker-reported position.
        
        Args:
            symbol: Trading symbol (required if order_executor is set)
            
        Returns:
            True if positions match, False if discrepancy detected
        """
        if self.order_executor is None:
            logger.debug("No order executor configured, skipping reconciliation")
            return True
        
        if symbol is None:
            logger.warning("Symbol required for position reconciliation")
            return True
        
        # Calculate expected net position
        expected_net = self.get_net_position()
        
        try:
            # Query broker for actual position
            actual_net = self.order_executor.get_broker_position(symbol)
            
            if expected_net != actual_net:
                logger.error(f"POSITION MISMATCH: Expected {expected_net}, Actual {actual_net}, "
                           f"Difference: {actual_net - expected_net}")
                
                # Log detailed book state
                logger.error(f"TrendBook: {self.trend_book}")
                logger.error(f"MRBook: {self.mr_book}")
                
                # TODO: Send Telegram alert
                # telegram_bot.send_alert(
                #     f"⚠️ POSITION MISMATCH\n"
                #     f"Expected: {expected_net}\n"
                #     f"Actual: {actual_net}\n"
                #     f"Difference: {actual_net - expected_net}"
                # )
                
                return False
            
            logger.debug(f"Position reconciliation OK: {expected_net}")
            return True
            
        except Exception as e:
            logger.error(f"Position reconciliation failed: {e}")
            return False
    
    def get_total_unrealized_pnl(self, current_price: float) -> float:
        """
        Calculate total unrealized P&L across both books.
        
        Args:
            current_price: Current market price
            
        Returns:
            Total unrealized P&L
        """
        trend_pnl = self.trend_book.get_unrealized_pnl(current_price)
        mr_pnl = self.mr_book.get_unrealized_pnl(current_price)
        return trend_pnl + mr_pnl
    
    def __repr__(self) -> str:
        """String representation of PositionManager."""
        return (f"PositionManager(net_position={self.get_net_position()}, "
                f"trend={self.trend_book}, mr={self.mr_book})")
