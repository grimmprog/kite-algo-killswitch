"""Market Data Settings API endpoints.

Requirements covered:
- 8.7: GET /api/v1/settings/market-data/sources — returns user's data source config with warnings
- 8.8: PUT /api/v1/settings/market-data/sources — accepts and persists data source config
- 8.9: Authentication required on all endpoints

Endpoints:
- GET  /api/v1/settings/market-data/sources  — Get data source configuration with warnings
- PUT  /api/v1/settings/market-data/sources  — Update data source configuration
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_current_user
from src.database.models.broker_connection import BrokerConnection
from src.services.market_data_service import (
    DataSourceConfig,
    DataSourceValidationError,
    MarketDataService,
)
from src.cache.redis_client import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings/market-data", tags=["market-data-settings"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class DataSourcesRequest(BaseModel):
    """Request body for updating data source configuration."""

    sources: List[DataSourceConfig]


class DataSourcesResponse(BaseModel):
    """Response body for data source configuration with warnings."""

    sources: List[DataSourceConfig]
    warnings: List[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_broker_warnings(db: Session, user_id: int, sources: List[DataSourceConfig]) -> List[str]:
    """Generate warnings for broker-dependent sources that are enabled but disconnected.

    Checks if Kite Historical Data or Dhan Market Data sources are enabled
    but the respective broker connection is not active.

    Args:
        db: SQLAlchemy session.
        user_id: The user's ID.
        sources: The user's current data source configuration.

    Returns:
        List of warning strings.
    """
    warnings: List[str] = []

    # Check which broker-dependent sources are enabled
    kite_enabled = any(
        s.source_id == "kite_historical" and s.enabled for s in sources
    )
    dhan_enabled = any(
        s.source_id == "dhan_market" and s.enabled for s in sources
    )

    if kite_enabled:
        kite_connection = (
            db.query(BrokerConnection)
            .filter(
                BrokerConnection.user_id == user_id,
                BrokerConnection.broker_type == "kite",
            )
            .first()
        )
        if kite_connection is None or kite_connection.status != "connected":
            warnings.append(
                "Kite Historical Data is enabled but Kite connection is not active. "
                "Please connect Kite in the Brokers tab."
            )

    if dhan_enabled:
        dhan_connection = (
            db.query(BrokerConnection)
            .filter(
                BrokerConnection.user_id == user_id,
                BrokerConnection.broker_type == "dhan",
            )
            .first()
        )
        if dhan_connection is None or dhan_connection.status != "connected":
            warnings.append(
                "Dhan Market Data is enabled but Dhan connection is not active. "
                "Please connect Dhan in the Brokers tab."
            )

    return warnings


# ---------------------------------------------------------------------------
# GET /api/v1/settings/market-data/sources
# ---------------------------------------------------------------------------


@router.get("/sources", response_model=DataSourcesResponse)
async def get_data_sources(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the user's data source configuration with broker connection warnings.

    Returns the list of data sources (enabled/disabled, priority ordered)
    and any warnings about broker-dependent sources that require an active
    connection.

    Implements Requirements 8.7, 8.9.
    """
    redis_client = get_redis_client()
    service = MarketDataService(db=db, redis_client=redis_client)

    sources = service.get_user_sources(user_id)
    warnings = _get_broker_warnings(db, user_id, sources)

    return DataSourcesResponse(sources=sources, warnings=warnings)


# ---------------------------------------------------------------------------
# PUT /api/v1/settings/market-data/sources
# ---------------------------------------------------------------------------


@router.put("/sources", response_model=DataSourcesResponse)
async def update_data_sources(
    body: DataSourcesRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the user's data source configuration.

    Validates that at least one source is enabled, then persists the
    configuration. Returns the updated configuration with any warnings.

    Returns 422 if all sources are disabled.

    Implements Requirements 8.8, 8.9.
    """
    redis_client = get_redis_client()
    service = MarketDataService(db=db, redis_client=redis_client)

    try:
        service.update_user_sources(user_id, body.sources)
    except DataSourceValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    # Re-read persisted sources to return the canonical state
    sources = service.get_user_sources(user_id)
    warnings = _get_broker_warnings(db, user_id, sources)

    return DataSourcesResponse(sources=sources, warnings=warnings)
