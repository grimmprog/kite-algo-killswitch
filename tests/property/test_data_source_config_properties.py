"""Property-based tests for Data Source Configuration Round-Trip (Property 6).

Uses Hypothesis to verify:
- Any valid data source configuration (list of sources with enabled/disabled states
  and priority ordering where at least one source is enabled), persisting via
  update_user_sources and then reading via get_user_sources SHALL return an
  equivalent configuration with the same enabled states and priority order.

**Validates: Requirements 6.6, 8.8**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from hypothesis import given, strategies as st, settings, assume
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from unittest.mock import MagicMock

from src.database.base import Base
from src.database.models.market_data_config import MarketDataSourceConfig
from src.services.market_data_service import (
    MarketDataService,
    DataSourceConfig,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database and session for each test."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def mock_redis():
    """Create a mock RedisClient."""
    return MagicMock()


@pytest.fixture
def service(db_session, mock_redis):
    """Create a MarketDataService with a real in-memory DB session."""
    return MarketDataService(db=db_session, redis_client=mock_redis)


# ============================================================
# Strategies
# ============================================================

# Valid source IDs as defined in the system
VALID_SOURCE_IDS = ["nsepy", "yfinance", "kite_historical", "dhan_market"]

DISPLAY_NAMES = {
    "nsepy": "NSEpy",
    "yfinance": "Yahoo Finance",
    "kite_historical": "Kite Historical Data",
    "dhan_market": "Dhan Market Data",
}


def data_source_config_strategy():
    """Generate a valid list of DataSourceConfig with at least one enabled.

    Strategy: Generate a subset of sources (1-4) with unique source_ids,
    random enabled states ensuring at least one is enabled, and unique
    sequential priorities.
    """
    return (
        st.lists(
            st.sampled_from(VALID_SOURCE_IDS),
            min_size=1,
            max_size=4,
            unique=True,
        )
        .flatmap(lambda source_ids: _build_configs(source_ids))
    )


def _build_configs(source_ids):
    """Build a list of DataSourceConfig from source_ids with valid constraints."""
    n = len(source_ids)
    # Generate enabled states as a list of booleans, then ensure at least one is True
    return st.lists(
        st.booleans(), min_size=n, max_size=n
    ).flatmap(
        lambda enabled_flags: _ensure_one_enabled(source_ids, enabled_flags)
    )


def _ensure_one_enabled(source_ids, enabled_flags):
    """Ensure at least one source is enabled, then build DataSourceConfig list."""
    # If none enabled, force the first one to be enabled
    if not any(enabled_flags):
        enabled_flags = list(enabled_flags)
        enabled_flags[0] = True

    # Generate a random permutation of priorities [0, 1, ..., n-1]
    n = len(source_ids)
    return st.permutations(list(range(n))).map(
        lambda priorities: [
            DataSourceConfig(
                source_id=source_ids[i],
                display_name=DISPLAY_NAMES[source_ids[i]],
                enabled=enabled_flags[i],
                priority=priorities[i],
            )
            for i in range(n)
        ]
    )


# ============================================================
# Property 6: Data Source Configuration Round-Trip
# ============================================================


class TestDataSourceConfigRoundTrip:
    """Property-based tests for data source configuration round-trip.

    **Validates: Requirements 6.6, 8.8**

    Core invariant:
    - For any valid data source configuration (at least one enabled),
      update_user_sources followed by get_user_sources returns an equivalent
      configuration with the same enabled states and priority order.
    """

    @given(configs=data_source_config_strategy())
    @settings(max_examples=100, deadline=None)
    def test_round_trip_preserves_config(self, configs):
        """Any valid config survives persist→read unchanged.

        **Validates: Requirements 6.6, 8.8**

        Property: For any valid data source configuration (list of sources with
        enabled/disabled states and priority ordering where at least one source
        is enabled), persisting via update_user_sources and then reading via
        get_user_sources SHALL return an equivalent configuration with the same
        enabled states and priority order.
        """
        # Set up fresh in-memory DB for each example
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            mock_redis = MagicMock()
            service = MarketDataService(db=session, redis_client=mock_redis)

            user_id = 1

            # Persist the configuration
            service.update_user_sources(user_id=user_id, sources=configs)

            # Read it back
            result = service.get_user_sources(user_id=user_id)

            # Verify same number of sources
            assert len(result) == len(configs)

            # Build lookup by source_id for comparison
            original_by_id = {c.source_id: c for c in configs}
            result_by_id = {r.source_id: r for r in result}

            # Same set of source_ids
            assert set(original_by_id.keys()) == set(result_by_id.keys())

            # Each source has same enabled state and priority
            for source_id in original_by_id:
                orig = original_by_id[source_id]
                res = result_by_id[source_id]

                assert res.enabled == orig.enabled, (
                    f"Source {source_id}: expected enabled={orig.enabled}, "
                    f"got enabled={res.enabled}"
                )
                assert res.priority == orig.priority, (
                    f"Source {source_id}: expected priority={orig.priority}, "
                    f"got priority={res.priority}"
                )
                assert res.display_name == orig.display_name, (
                    f"Source {source_id}: expected display_name='{orig.display_name}', "
                    f"got display_name='{res.display_name}'"
                )

            # Verify result is sorted by priority (ascending)
            priorities = [r.priority for r in result]
            assert priorities == sorted(priorities), (
                f"Result not sorted by priority: {priorities}"
            )

        engine.dispose()

    @given(configs=data_source_config_strategy())
    @settings(max_examples=50, deadline=None)
    def test_round_trip_idempotent(self, configs):
        """Persisting the same config twice still reads back correctly.

        **Validates: Requirements 6.6, 8.8**

        Property: Writing the same configuration twice in succession should
        produce the same result when read back (idempotent persistence).
        """
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            mock_redis = MagicMock()
            service = MarketDataService(db=session, redis_client=mock_redis)

            user_id = 1

            # Write config twice
            service.update_user_sources(user_id=user_id, sources=configs)
            service.update_user_sources(user_id=user_id, sources=configs)

            # Read back
            result = service.get_user_sources(user_id=user_id)

            # Still matches original
            assert len(result) == len(configs)

            original_by_id = {c.source_id: c for c in configs}
            result_by_id = {r.source_id: r for r in result}

            for source_id in original_by_id:
                orig = original_by_id[source_id]
                res = result_by_id[source_id]
                assert res.enabled == orig.enabled
                assert res.priority == orig.priority
                assert res.display_name == orig.display_name

        engine.dispose()
