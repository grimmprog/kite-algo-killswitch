"""Property-based tests for Data Source Priority Fallback (Property 10).

Uses Hypothesis to verify:
- For any ordered list of N enabled data sources where the first K sources
  (K < N) fail with timeout or error, the system SHALL attempt to fetch from
  source K+1. The returned data SHALL be attributed to the first source that
  succeeds.

**Validates: Requirements 7.5, 7.6**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from hypothesis import given, strategies as st, settings, assume
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from unittest.mock import MagicMock, patch

from src.database.base import Base
from src.database.models.market_data_config import MarketDataSourceConfig
from src.services.market_data_service import (
    MarketDataService,
    DataSourceConfig,
    IndexData,
    LiveMarketResponse,
)


# ============================================================
# Strategies
# ============================================================

VALID_SOURCE_IDS = ["nsepy", "yfinance", "kite_historical", "dhan_market"]

DISPLAY_NAMES = {
    "nsepy": "NSEpy",
    "yfinance": "Yahoo Finance",
    "kite_historical": "Kite Historical Data",
    "dhan_market": "Dhan Market Data",
}


def source_list_and_failure_count():
    """Generate a list of N enabled sources (2-4) with unique priorities,
    and K (0 to N-1) representing how many sources fail before one succeeds.
    """
    return (
        st.integers(min_value=2, max_value=4)
        .flatmap(lambda n: _build_sources_and_k(n))
    )


def _build_sources_and_k(n):
    """Build N sources from the valid pool with unique priorities, plus K."""
    return st.tuples(
        # Pick n unique source_ids
        st.lists(
            st.sampled_from(VALID_SOURCE_IDS),
            min_size=n,
            max_size=n,
            unique=True,
        ),
        # Pick a permutation of priorities 0..n-1
        st.permutations(list(range(n))),
        # K: number of sources that fail (0 to n-1)
        st.integers(min_value=0, max_value=n - 1),
    )


# ============================================================
# Property 10: Data Source Priority Fallback
# ============================================================


class TestDataSourcePriorityFallback:
    """Property-based tests for data source priority fallback.

    **Validates: Requirements 7.5, 7.6**

    Core invariant:
    - For any ordered list of N enabled data sources where the first K sources
      (K < N) fail with timeout or error, the system SHALL attempt to fetch from
      source K+1. The returned data SHALL be attributed to the first source
      that succeeds.
    """

    @given(data=source_list_and_failure_count())
    @settings(max_examples=100, deadline=None)
    def test_fallback_attributes_to_first_successful_source(self, data):
        """When first K sources fail, result is attributed to source K+1.

        **Validates: Requirements 7.5, 7.6**

        Property: For any ordered list of N enabled data sources where the
        first K sources (K < N) fail with timeout or error, the system SHALL
        attempt to fetch from source K+1. The returned data SHALL be attributed
        to the first source that succeeds.
        """
        source_ids, priorities, k = data

        n = len(source_ids)

        # Build DataSourceConfig entries — all enabled
        configs = [
            DataSourceConfig(
                source_id=source_ids[i],
                display_name=DISPLAY_NAMES[source_ids[i]],
                enabled=True,
                priority=priorities[i],
            )
            for i in range(n)
        ]

        # Sort by priority to determine the call order
        sorted_configs = sorted(configs, key=lambda c: c.priority)

        # The source that should succeed is at index K in priority order
        expected_source_id = sorted_configs[k].source_id

        # Set up in-memory DB and persist the sources
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            mock_redis = MagicMock()
            # Make redis.get return None (cache miss)
            mock_redis.get.return_value = None

            service = MarketDataService(db=session, redis_client=mock_redis)

            user_id = 1

            # Persist sources
            service.update_user_sources(user_id=user_id, sources=configs)

            # Track call count to _fetch_from_source
            call_count = [0]
            sources_attempted = []

            # Build mock for _fetch_from_source that fails for first K calls
            # and succeeds on call K+1
            def mock_fetch(source_id, uid):
                sources_attempted.append(source_id)
                call_count[0] += 1
                if call_count[0] <= k:
                    raise ConnectionError(
                        f"Simulated failure for source {source_id}"
                    )
                # Succeed with dummy data
                return [
                    IndexData(
                        symbol="NIFTY 50",
                        value=22000.0,
                        change_points=100.0,
                        change_percent=0.46,
                        last_updated="2024-01-01T10:00:00",
                    )
                ]

            # Patch _fetch_from_source on the service instance
            service._fetch_from_source = mock_fetch

            # Execute
            response = service.fetch_live_indices(user_id=user_id)

            # Verify attribution
            assert response.data_source == expected_source_id, (
                f"Expected data_source='{expected_source_id}', "
                f"got '{response.data_source}'. "
                f"K={k}, priority order={[c.source_id for c in sorted_configs]}, "
                f"sources attempted={sources_attempted}"
            )

            # Verify exactly K+1 sources were attempted
            assert call_count[0] == k + 1, (
                f"Expected {k + 1} fetch attempts, got {call_count[0]}"
            )

            # Verify the first K sources attempted match the first K in
            # priority order
            expected_attempts = [c.source_id for c in sorted_configs[: k + 1]]
            assert sources_attempted == expected_attempts, (
                f"Expected attempts order {expected_attempts}, "
                f"got {sources_attempted}"
            )

        engine.dispose()

    @given(data=source_list_and_failure_count())
    @settings(max_examples=50, deadline=None)
    def test_fallback_skips_failed_sources_correctly(self, data):
        """Failed sources are skipped and next priority source is tried.

        **Validates: Requirements 7.5, 7.6**

        Property: Each failed source triggers an attempt on the next source
        in priority order, never skipping or re-trying a failed source.
        """
        source_ids, priorities, k = data

        n = len(source_ids)

        configs = [
            DataSourceConfig(
                source_id=source_ids[i],
                display_name=DISPLAY_NAMES[source_ids[i]],
                enabled=True,
                priority=priorities[i],
            )
            for i in range(n)
        ]

        sorted_configs = sorted(configs, key=lambda c: c.priority)

        # Set up in-memory DB
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            mock_redis = MagicMock()
            mock_redis.get.return_value = None

            service = MarketDataService(db=session, redis_client=mock_redis)

            user_id = 1
            service.update_user_sources(user_id=user_id, sources=configs)

            # Track which sources were called
            sources_called = []

            def mock_fetch(source_id, uid):
                sources_called.append(source_id)
                idx = next(
                    i for i, c in enumerate(sorted_configs)
                    if c.source_id == source_id
                )
                if idx < k:
                    raise TimeoutError(
                        f"Timeout for source {source_id}"
                    )
                return [
                    IndexData(
                        symbol="SENSEX",
                        value=73000.0,
                        change_points=-50.0,
                        change_percent=-0.07,
                        last_updated="2024-01-01T10:00:00",
                    )
                ]

            service._fetch_from_source = mock_fetch

            response = service.fetch_live_indices(user_id=user_id)

            # No source should be called twice
            assert len(sources_called) == len(set(sources_called)), (
                f"Sources called multiple times: {sources_called}"
            )

            # Sources are called in strict priority order
            expected_order = [c.source_id for c in sorted_configs[: k + 1]]
            assert sources_called == expected_order, (
                f"Expected call order {expected_order}, got {sources_called}"
            )

        engine.dispose()
