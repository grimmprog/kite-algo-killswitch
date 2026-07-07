"""Property-based tests for at-least-one-source validation (Task 3.3).

Uses Hypothesis to verify:
- Property 7: At Least One Data Source Validation — all-disabled configs are rejected,
  existing config unchanged.

**Validates: Requirements 6.7**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from hypothesis import given, strategies as st, settings, assume
from unittest.mock import MagicMock

from src.services.market_data_service import (
    MarketDataService,
    DataSourceConfig,
    DataSourceValidationError,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

VALID_SOURCE_IDS = ["nsepy", "yfinance", "kite_historical", "dhan_market"]
VALID_DISPLAY_NAMES = {
    "nsepy": "NSEpy",
    "yfinance": "Yahoo Finance",
    "kite_historical": "Kite Historical Data",
    "dhan_market": "Dhan Market Data",
}


def all_disabled_source_configs_strategy():
    """Generate lists of DataSourceConfig where ALL entries have enabled=False.

    Produces 1-4 sources drawn from valid source IDs, each with unique priorities
    and enabled=False.
    """
    return st.lists(
        st.sampled_from(VALID_SOURCE_IDS),
        min_size=1,
        max_size=4,
        unique=True,
    ).map(
        lambda source_ids: [
            DataSourceConfig(
                source_id=sid,
                display_name=VALID_DISPLAY_NAMES[sid],
                enabled=False,
                priority=i,
            )
            for i, sid in enumerate(source_ids)
        ]
    )


# ============================================================
# Property 7: At Least One Data Source Validation
# ============================================================


class TestAtLeastOneDataSourceValidation:
    """Property-based tests for at-least-one-source validation.

    **Validates: Requirements 6.7**

    Core invariant:
    For any data source configuration where all sources have enabled=False,
    the update_user_sources function SHALL reject the configuration with a
    validation error and leave the existing configuration unchanged.
    """

    @given(sources=all_disabled_source_configs_strategy())
    @settings(max_examples=100, deadline=None)
    def test_all_disabled_sources_raises_validation_error(self, sources):
        """All-disabled source configs are rejected with DataSourceValidationError.

        **Validates: Requirements 6.7**

        Property: For any list of DataSourceConfig where every entry has
        enabled=False, update_user_sources raises DataSourceValidationError.
        """
        mock_db = MagicMock()
        mock_redis = MagicMock()
        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with pytest.raises(DataSourceValidationError):
            service.update_user_sources(user_id=1, sources=sources)

    @given(sources=all_disabled_source_configs_strategy())
    @settings(max_examples=100, deadline=None)
    def test_all_disabled_sources_error_message_correct(self, sources):
        """Error message matches expected text for all-disabled configs.

        **Validates: Requirements 6.7**

        Property: For any all-disabled config, the error message is exactly
        "At least one data source must be enabled".
        """
        mock_db = MagicMock()
        mock_redis = MagicMock()
        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with pytest.raises(DataSourceValidationError) as exc_info:
            service.update_user_sources(user_id=1, sources=sources)

        assert str(exc_info.value) == "At least one data source must be enabled"

    @given(sources=all_disabled_source_configs_strategy())
    @settings(max_examples=100, deadline=None)
    def test_all_disabled_sources_does_not_modify_database(self, sources):
        """Database is not modified when all-disabled config is rejected.

        **Validates: Requirements 6.7**

        Property: For any all-disabled config, no commit is called on the
        database session, meaning existing configuration remains unchanged.
        """
        mock_db = MagicMock()
        mock_redis = MagicMock()
        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with pytest.raises(DataSourceValidationError):
            service.update_user_sources(user_id=1, sources=sources)

        # Verify no database modifications occurred
        mock_db.commit.assert_not_called()
        mock_db.add.assert_not_called()
        mock_db.query.assert_not_called()

    @given(
        sources=all_disabled_source_configs_strategy(),
        user_id=st.integers(min_value=1, max_value=10000),
    )
    @settings(max_examples=50, deadline=None)
    def test_all_disabled_rejected_regardless_of_user_id(self, sources, user_id):
        """All-disabled validation is independent of user_id.

        **Validates: Requirements 6.7**

        Property: For any user_id and any all-disabled config, the validation
        error is raised consistently.
        """
        mock_db = MagicMock()
        mock_redis = MagicMock()
        service = MarketDataService(db=mock_db, redis_client=mock_redis)

        with pytest.raises(DataSourceValidationError):
            service.update_user_sources(user_id=user_id, sources=sources)

        mock_db.commit.assert_not_called()
