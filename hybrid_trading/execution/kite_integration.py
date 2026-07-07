"""
Integration with existing connect.py module for Kite API connectivity.

This module provides a bridge between the hybrid trading system and the existing
Zerodha Kite connection infrastructure.
"""

import logging
import sys
import os

# Add parent directory to path to import connect module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from connect import get_kite_session
from .order_executor import OrderExecutor, ExecutionConfig


logger = logging.getLogger(__name__)


def get_kite_connection():
    """
    Get KiteConnect instance using existing connect.py infrastructure.
    
    This function uses the existing TOTP-based login flow from connect.py.
    
    Returns:
        KiteConnect instance
        
    Raises:
        Exception if connection fails
    """
    try:
        logger.info("Establishing Kite connection...")
        kite = get_kite_session()
        
        # Verify connection by getting profile
        profile = kite.profile()
        logger.info(f"Connected to Kite as: {profile.get('user_name', 'Unknown')}")
        
        return kite
        
    except Exception as e:
        logger.error(f"Failed to establish Kite connection: {e}")
        raise


def create_order_executor(config: ExecutionConfig = None) -> OrderExecutor:
    """
    Create OrderExecutor with Kite connection.
    
    Args:
        config: Execution configuration (uses defaults if None)
        
    Returns:
        OrderExecutor instance
        
    Raises:
        Exception if connection fails
    """
    if config is None:
        config = ExecutionConfig()
    
    kite = get_kite_connection()
    executor = OrderExecutor(kite, config)
    
    logger.info("OrderExecutor created successfully")
    
    return executor


def test_connection():
    """
    Test Kite connection and basic API functionality.
    
    Returns:
        True if connection successful, False otherwise
    """
    try:
        kite = get_kite_connection()
        
        # Test profile access
        profile = kite.profile()
        print(f"✓ Profile access successful: {profile.get('user_name')}")
        
        # Test positions query
        positions = kite.positions()
        print(f"✓ Positions query successful: {len(positions.get('net', []))} positions")
        
        # Test orders query
        orders = kite.orders()
        print(f"✓ Orders query successful: {len(orders)} orders")
        
        print("\n✓ All connection tests passed!")
        return True
        
    except Exception as e:
        print(f"\n✗ Connection test failed: {e}")
        return False


if __name__ == '__main__':
    # Run connection test when module is executed directly
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("Testing Kite connection...\n")
    test_connection()
