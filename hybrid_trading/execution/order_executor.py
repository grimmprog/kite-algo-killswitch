"""
Order Executor for Zerodha Kite API integration.

This module handles order placement, confirmation, retry logic, and trade ledger maintenance.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from kiteconnect import KiteConnect

from .models import Signal, OrderResult
from ..common.enums import SignalType


logger = logging.getLogger(__name__)


@dataclass
class LedgerEntry:
    """Represents an entry in the trade ledger."""
    timestamp: datetime
    order_id: str
    signal: Signal
    order_result: OrderResult
    book: str  # 'trend' or 'mr'
    attempt_number: int = 1


@dataclass
class ExecutionConfig:
    """Configuration for order execution."""
    symbol: str = 'NIFTY24JANFUT'
    exchange: str = 'NFO'
    order_timeout: int = 10  # seconds
    use_limit_orders: bool = False
    limit_order_offset_pct: float = 0.1  # 0.1% offset for limit orders
    max_retry_attempts: int = 3
    retry_backoff_base: float = 2.0  # exponential backoff base


class OrderExecutor:
    """
    Handles order execution with Zerodha Kite API.
    
    Features:
    - Order placement with MARKET/LIMIT order type selection
    - Order confirmation waiting with timeout
    - Retry logic with exponential backoff (max 3 attempts)
    - Internal trade ledger for all orders
    - Broker position query
    """
    
    def __init__(self, kite: KiteConnect, config: ExecutionConfig):
        """
        Initialize OrderExecutor.
        
        Args:
            kite: KiteConnect instance
            config: Execution configuration
        """
        self.kite = kite
        self.config = config
        self.trade_ledger: List[LedgerEntry] = []
        
        logger.info(f"OrderExecutor initialized for {config.symbol} on {config.exchange}")
    
    def place_order(self, signal: Signal, order_type: Optional[str] = None, 
                    transaction_type: Optional[str] = None) -> OrderResult:
        """
        Place order with Zerodha Kite API.
        
        Implements:
        - Order type selection (MARKET for exits, LIMIT for entries)
        - Order confirmation waiting with timeout
        - Retry logic with exponential backoff (max 3 attempts)
        - Trade ledger recording
        
        Args:
            signal: Trading signal to execute
            order_type: Override order type ('MARKET' or 'LIMIT'). If None, auto-select.
            transaction_type: Override transaction type ('BUY' or 'SELL'). If None, auto-determine.
            
        Returns:
            OrderResult with execution details
        """
        # Auto-select order type if not specified
        if order_type is None:
            order_type = self._select_order_type(signal)
        
        logger.info(f"Placing {order_type} order for signal: {signal.signal_type} "
                   f"qty={signal.quantity} engine={signal.engine}")
        
        # Store transaction_type for use in attempts
        self._override_transaction_type = transaction_type
        
        # Retry logic with exponential backoff
        for attempt in range(1, self.config.max_retry_attempts + 1):
            try:
                order_result = self._place_order_attempt(signal, order_type, attempt)
                
                # Log to trade ledger
                self._log_to_ledger(signal, order_result, attempt)
                
                if order_result.is_complete:
                    logger.info(f"Order completed: {order_result.order_id} "
                               f"filled={order_result.filled_quantity} "
                               f"avg_price={order_result.average_price:.2f}")
                    
                    # Clean up override
                    if hasattr(self, '_override_transaction_type'):
                        delattr(self, '_override_transaction_type')
                    
                    return order_result
                
                elif order_result.is_rejected:
                    logger.error(f"Order rejected: {order_result.message}")
                    
                    # Clean up override
                    if hasattr(self, '_override_transaction_type'):
                        delattr(self, '_override_transaction_type')
                    
                    # Don't retry if rejected (likely invalid order)
                    return order_result
                
                # If pending, wait and retry
                logger.warning(f"Order attempt {attempt} pending, will retry...")
                
                # Exponential backoff
                if attempt < self.config.max_retry_attempts:
                    backoff_time = self.config.retry_backoff_base ** attempt
                    logger.info(f"Waiting {backoff_time:.1f}s before retry...")
                    time.sleep(backoff_time)
                
            except Exception as e:
                logger.error(f"Order attempt {attempt} failed with exception: {e}")
                
                # Create failed order result
                order_result = OrderResult(
                    order_id='',
                    status='REJECTED',
                    filled_quantity=0,
                    average_price=0.0,
                    message=f"Exception on attempt {attempt}: {str(e)}"
                )
                
                # Log to ledger
                self._log_to_ledger(signal, order_result, attempt)
                
                # Retry with backoff
                if attempt < self.config.max_retry_attempts:
                    backoff_time = self.config.retry_backoff_base ** attempt
                    logger.info(f"Waiting {backoff_time:.1f}s before retry...")
                    time.sleep(backoff_time)
                else:
                    # Final attempt failed
                    logger.error(f"Order failed after {self.config.max_retry_attempts} attempts")
                    return order_result
        
        # All attempts exhausted
        final_result = OrderResult(
            order_id='',
            status='REJECTED',
            filled_quantity=0,
            average_price=0.0,
            message=f'Max retries ({self.config.max_retry_attempts}) exceeded'
        )
        
        # Clean up override
        if hasattr(self, '_override_transaction_type'):
            delattr(self, '_override_transaction_type')
        
        return final_result
    
    def _place_order_attempt(self, signal: Signal, order_type: str, attempt: int) -> OrderResult:
        """
        Single order placement attempt.
        
        Args:
            signal: Trading signal
            order_type: 'MARKET' or 'LIMIT'
            attempt: Attempt number
            
        Returns:
            OrderResult
        """
        # Determine transaction type
        transaction_type = self._get_transaction_type(signal)
        
        # Build order parameters
        order_params = {
            'tradingsymbol': self.config.symbol,
            'exchange': self.config.exchange,
            'transaction_type': transaction_type,
            'quantity': signal.quantity,
            'order_type': order_type,
            'product': 'MIS',  # Intraday
            'validity': 'DAY'
        }
        
        # Add limit price if using LIMIT orders
        if order_type == 'LIMIT':
            limit_price = self._calculate_limit_price(signal, transaction_type)
            order_params['price'] = limit_price
            logger.debug(f"Limit price set to {limit_price:.2f}")
        
        # Place order via Kite API
        logger.debug(f"Placing order with params: {order_params}")
        order_id = self.kite.place_order(variety=self.kite.VARIETY_REGULAR, **order_params)
        
        logger.info(f"Order placed: {order_id}")
        
        # Wait for order confirmation
        order_status = self._wait_for_order_fill(order_id, timeout=self.config.order_timeout)
        
        return order_status
    
    def _select_order_type(self, signal: Signal) -> str:
        """
        Select order type based on signal.
        
        Rule: MARKET for exits, LIMIT for entries (if configured)
        
        Args:
            signal: Trading signal
            
        Returns:
            'MARKET' or 'LIMIT'
        """
        # Always use MARKET for exits (urgent)
        if signal.signal_type.is_exit:
            return 'MARKET'
        
        # Use LIMIT for entries if configured
        if signal.signal_type.is_entry and self.config.use_limit_orders:
            return 'LIMIT'
        
        # Default to MARKET
        return 'MARKET'
    
    def _get_transaction_type(self, signal: Signal) -> str:
        """
        Determine transaction type (BUY/SELL) from signal.
        
        For exits, the caller (PositionManager) should provide the transaction_type
        explicitly since it knows the position direction.
        
        Args:
            signal: Trading signal
            
        Returns:
            'BUY' or 'SELL'
        """
        # Check if transaction type was overridden
        if hasattr(self, '_override_transaction_type') and self._override_transaction_type:
            return self._override_transaction_type
        
        if signal.signal_type == SignalType.ENTRY_LONG:
            return 'BUY'
        elif signal.signal_type == SignalType.ENTRY_SHORT:
            return 'SELL'
        elif signal.signal_type in [SignalType.EXIT_PARTIAL, SignalType.EXIT_FULL]:
            # For exits, we need position context which should be provided by caller
            # This is a fallback that will raise an error
            raise ValueError(
                f"Cannot determine transaction type for exit signal without position context. "
                f"Signal: {signal.signal_type}, Engine: {signal.engine}. "
                f"Caller must provide transaction_type parameter."
            )
        else:
            raise ValueError(f"Unknown signal type: {signal.signal_type}")
    
    def _calculate_limit_price(self, signal: Signal, transaction_type: str) -> float:
        """
        Calculate limit price with offset from signal price.
        
        Args:
            signal: Trading signal
            transaction_type: 'BUY' or 'SELL'
            
        Returns:
            Limit price
        """
        offset_pct = self.config.limit_order_offset_pct / 100.0
        
        if transaction_type == 'BUY':
            # Buy slightly above current price
            limit_price = signal.price * (1 + offset_pct)
        else:  # SELL
            # Sell slightly below current price
            limit_price = signal.price * (1 - offset_pct)
        
        return round(limit_price, 2)
    
    def _wait_for_order_fill(self, order_id: str, timeout: int) -> OrderResult:
        """
        Wait for order to fill with timeout.
        
        Args:
            order_id: Order ID from Kite
            timeout: Timeout in seconds
            
        Returns:
            OrderResult
        """
        start_time = time.time()
        poll_interval = 0.5  # Poll every 0.5 seconds
        
        while time.time() - start_time < timeout:
            try:
                # Query order status
                orders = self.kite.orders()
                
                # Find our order
                order = None
                for o in orders:
                    if o['order_id'] == order_id:
                        order = o
                        break
                
                if order is None:
                    logger.warning(f"Order {order_id} not found in order list")
                    time.sleep(poll_interval)
                    continue
                
                # Check order status
                status = order['status']
                
                if status == 'COMPLETE':
                    return OrderResult(
                        order_id=order_id,
                        status='COMPLETE',
                        filled_quantity=order['filled_quantity'],
                        average_price=order['average_price'],
                        message='Order filled successfully'
                    )
                
                elif status in ['REJECTED', 'CANCELLED']:
                    return OrderResult(
                        order_id=order_id,
                        status=status,
                        filled_quantity=order.get('filled_quantity', 0),
                        average_price=order.get('average_price', 0.0),
                        message=order.get('status_message', f'Order {status.lower()}')
                    )
                
                # Order still pending, continue polling
                time.sleep(poll_interval)
                
            except Exception as e:
                logger.error(f"Error checking order status: {e}")
                time.sleep(poll_interval)
        
        # Timeout reached
        logger.warning(f"Order {order_id} confirmation timeout after {timeout}s")
        
        return OrderResult(
            order_id=order_id,
            status='PENDING',
            filled_quantity=0,
            average_price=0.0,
            message=f'Order confirmation timeout after {timeout}s'
        )
    
    def _log_to_ledger(self, signal: Signal, order_result: OrderResult, attempt: int):
        """
        Log order to internal trade ledger.
        
        Args:
            signal: Trading signal
            order_result: Order execution result
            attempt: Attempt number
        """
        entry = LedgerEntry(
            timestamp=datetime.now(),
            order_id=order_result.order_id,
            signal=signal,
            order_result=order_result,
            book=signal.engine,
            attempt_number=attempt
        )
        
        self.trade_ledger.append(entry)
        
        logger.debug(f"Logged to trade ledger: order_id={order_result.order_id} "
                    f"status={order_result.status} attempt={attempt}")
    
    def get_broker_position(self, symbol: Optional[str] = None) -> int:
        """
        Get current position from broker.
        
        Args:
            symbol: Trading symbol (uses config.symbol if None)
            
        Returns:
            Net position quantity (positive for long, negative for short)
        """
        if symbol is None:
            symbol = self.config.symbol
        
        try:
            positions = self.kite.positions()
            
            # Check net positions
            net_positions = positions.get('net', [])
            
            for pos in net_positions:
                if pos['tradingsymbol'] == symbol:
                    quantity = pos['quantity']
                    logger.debug(f"Broker position for {symbol}: {quantity}")
                    return quantity
            
            # Position not found, return 0
            logger.debug(f"No position found for {symbol}")
            return 0
            
        except Exception as e:
            logger.error(f"Error querying broker position: {e}")
            raise
    
    def get_trade_ledger(self) -> List[LedgerEntry]:
        """
        Get complete trade ledger.
        
        Returns:
            List of ledger entries
        """
        return self.trade_ledger.copy()
    
    def get_ledger_summary(self) -> dict:
        """
        Get summary statistics from trade ledger.
        
        Returns:
            Dictionary with summary stats
        """
        total_orders = len(self.trade_ledger)
        completed = sum(1 for e in self.trade_ledger if e.order_result.is_complete)
        rejected = sum(1 for e in self.trade_ledger if e.order_result.is_rejected)
        pending = sum(1 for e in self.trade_ledger if e.order_result.is_pending)
        
        trend_orders = sum(1 for e in self.trade_ledger if e.book == 'trend')
        mr_orders = sum(1 for e in self.trade_ledger if e.book == 'mr')
        
        return {
            'total_orders': total_orders,
            'completed': completed,
            'rejected': rejected,
            'pending': pending,
            'trend_orders': trend_orders,
            'mr_orders': mr_orders,
            'success_rate': (completed / total_orders * 100) if total_orders > 0 else 0.0
        }
