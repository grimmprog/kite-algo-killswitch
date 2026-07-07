"""
Cache Invalidation Module for Multi-User Web Trading Platform.

Provides functions to invalidate (delete) cached data from Redis for
specific users or market symbols. Each function handles errors gracefully
by logging failures and returning a boolean success indicator.

Validates: Requirements 3.6.1, 3.6.2, 3.6.3, 3.6.4, 3.6.5, 3.6.10
"""

import logging
from typing import Union

from src.cache.redis_client import get_redis_client
from src.cache.redis_keys import RedisKeys

logger = logging.getLogger(__name__)


def invalidate_user_risk(user_id: int) -> bool:
    """Delete the user's risk metrics cache.

    Removes the Redis hash at key `user:{user_id}:risk`.

    Args:
        user_id: The user's database ID.

    Returns:
        True if the key was successfully deleted (or didn't exist), False on error.
    """
    try:
        client = get_redis_client()
        key = RedisKeys.user_risk(user_id)
        client.delete(key)
        logger.info("Invalidated risk cache for user %d", user_id)
        return True
    except Exception as e:
        logger.error("Failed to invalidate risk cache for user %d: %s", user_id, e)
        return False


def invalidate_user_killswitch(user_id: int) -> bool:
    """Delete the user's killswitch flag from cache.

    Removes the Redis string at key `user:{user_id}:killswitch`.

    Args:
        user_id: The user's database ID.

    Returns:
        True if the key was successfully deleted (or didn't exist), False on error.
    """
    try:
        client = get_redis_client()
        key = RedisKeys.user_killswitch(user_id)
        client.delete(key)
        logger.info("Invalidated killswitch cache for user %d", user_id)
        return True
    except Exception as e:
        logger.error("Failed to invalidate killswitch cache for user %d: %s", user_id, e)
        return False


def invalidate_user_recent_orders(user_id: int) -> bool:
    """Delete the user's recent orders list from cache.

    Removes the Redis list at key `user:{user_id}:recent_orders`.

    Args:
        user_id: The user's database ID.

    Returns:
        True if the key was successfully deleted (or didn't exist), False on error.
    """
    try:
        client = get_redis_client()
        key = RedisKeys.user_recent_orders(user_id)
        client.delete(key)
        logger.info("Invalidated recent orders cache for user %d", user_id)
        return True
    except Exception as e:
        logger.error("Failed to invalidate recent orders cache for user %d: %s", user_id, e)
        return False


def invalidate_market_data(symbol: str) -> bool:
    """Delete cached market data for a symbol.

    Removes the Redis string (JSON) at key `market:{symbol}:data`.

    Args:
        symbol: Trading symbol, e.g. "NIFTY" or "BANKNIFTY".

    Returns:
        True if the key was successfully deleted (or didn't exist), False on error.
    """
    try:
        client = get_redis_client()
        key = RedisKeys.market_data(symbol)
        client.delete(key)
        logger.info("Invalidated market data cache for symbol %s", symbol)
        return True
    except Exception as e:
        logger.error("Failed to invalidate market data cache for symbol %s: %s", symbol, e)
        return False


def invalidate_market_ticks(symbol: str) -> bool:
    """Delete cached market ticks for a symbol.

    Removes the Redis list at key `market:{symbol}:ticks`.

    Args:
        symbol: Trading symbol, e.g. "NIFTY" or "BANKNIFTY".

    Returns:
        True if the key was successfully deleted (or didn't exist), False on error.
    """
    try:
        client = get_redis_client()
        key = RedisKeys.market_ticks(symbol)
        client.delete(key)
        logger.info("Invalidated market ticks cache for symbol %s", symbol)
        return True
    except Exception as e:
        logger.error("Failed to invalidate market ticks cache for symbol %s: %s", symbol, e)
        return False


def invalidate_all_user_cache(user_id: int) -> bool:
    """Delete ALL cache entries for a user.

    Removes risk metrics, killswitch flag, and recent orders cache
    for the specified user.

    Args:
        user_id: The user's database ID.

    Returns:
        True if all keys were successfully deleted, False if any deletion failed.
    """
    try:
        client = get_redis_client()
        keys = [
            RedisKeys.user_risk(user_id),
            RedisKeys.user_killswitch(user_id),
            RedisKeys.user_recent_orders(user_id),
        ]
        for key in keys:
            client.delete(key)
        logger.info("Invalidated all cache entries for user %d", user_id)
        return True
    except Exception as e:
        logger.error("Failed to invalidate all cache for user %d: %s", user_id, e)
        return False


def invalidate_all_market_cache(symbol: str) -> bool:
    """Delete ALL market cache entries for a symbol.

    Removes market data and market ticks cache for the specified symbol.

    Args:
        symbol: Trading symbol, e.g. "NIFTY" or "BANKNIFTY".

    Returns:
        True if all keys were successfully deleted, False if any deletion failed.
    """
    try:
        client = get_redis_client()
        keys = [
            RedisKeys.market_data(symbol),
            RedisKeys.market_ticks(symbol),
        ]
        for key in keys:
            client.delete(key)
        logger.info("Invalidated all market cache for symbol %s", symbol)
        return True
    except Exception as e:
        logger.error("Failed to invalidate all market cache for symbol %s: %s", symbol, e)
        return False
