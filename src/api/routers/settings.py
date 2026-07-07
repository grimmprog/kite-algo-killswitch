"""Settings API endpoints.

Requirements covered:
- 5.1-5.7: Strategy and Risk Settings
- 6.1-6.6: Kill Switch Thresholds Configuration
- 12.1-12.4: Segment Management
- 17.2: AI Settings Configuration

Endpoints:
- GET  /api/v1/settings/strategy            — Get strategy settings
- PUT  /api/v1/settings/strategy            — Update strategy settings
- GET  /api/v1/settings/killswitch          — Get kill switch thresholds
- PUT  /api/v1/settings/killswitch          — Update kill switch thresholds
- GET  /api/v1/settings/segments            — Get all segment statuses
- PUT  /api/v1/settings/segments/{segment}  — Toggle segment activation
- GET  /api/v1/settings/ai                  — Get AI settings
- PUT  /api/v1/settings/ai                  — Update AI settings
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_current_user
from src.services.settings_service import (
    AISettings,
    KillSwitchThresholds,
    KillSwitchThresholdsResponse,
    SegmentStatus,
    SettingsService,
    StrategySettings,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["settings"])

# Shared service instance
_settings_service = SettingsService()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class SegmentToggleRequest(BaseModel):
    """Request body for toggling a segment."""

    activate: bool


class AISettingsUpdateRequest(BaseModel):
    """Request body for updating AI settings."""

    provider: str | None = None
    signal_analysis_enabled: bool | None = None
    entry_suggestions_enabled: bool | None = None
    exit_recommendations_enabled: bool | None = None
    market_narrative_enabled: bool | None = None
    trade_review_enabled: bool | None = None
    risk_warnings_enabled: bool | None = None


# ---------------------------------------------------------------------------
# GET /api/v1/settings/strategy
# ---------------------------------------------------------------------------


@router.get("/settings/strategy", response_model=StrategySettings)
async def get_strategy_settings(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current strategy settings for the authenticated user.

    Returns watchlist, trading times, confidence threshold, max trades,
    capital, and lot sizes.
    """
    try:
        return _settings_service.get_strategy_settings(db, user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ---------------------------------------------------------------------------
# PUT /api/v1/settings/strategy
# ---------------------------------------------------------------------------


@router.put("/settings/strategy", response_model=StrategySettings)
async def update_strategy_settings(
    settings: StrategySettings,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update strategy settings with validation.

    Validates:
    - Confidence threshold: 50-100
    - Trading start time before end time
    - Capital > 0
    - Max trades per day: 1-10
    """
    try:
        return _settings_service.update_strategy_settings(db, user_id, settings)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


# ---------------------------------------------------------------------------
# GET /api/v1/settings/killswitch
# ---------------------------------------------------------------------------


@router.get("/settings/killswitch", response_model=KillSwitchThresholdsResponse)
async def get_killswitch_thresholds(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get kill switch thresholds with computed absolute amounts.

    Returns threshold types, values, computed amounts, and a warning
    if daily loss exceeds 25% of capital.
    """
    try:
        return _settings_service.get_killswitch_thresholds(db, user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ---------------------------------------------------------------------------
# PUT /api/v1/settings/killswitch
# ---------------------------------------------------------------------------


@router.put("/settings/killswitch", response_model=KillSwitchThresholdsResponse)
async def update_killswitch_thresholds(
    thresholds: KillSwitchThresholds,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update kill switch thresholds with validation.

    Validates:
    - All threshold values are positive
    - Threshold types are 'percentage' or 'absolute'
    - Returns warning if daily loss > 25% of capital
    """
    try:
        return _settings_service.update_killswitch_thresholds(db, user_id, thresholds)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


# ---------------------------------------------------------------------------
# GET /api/v1/settings/segments
# ---------------------------------------------------------------------------


@router.get("/settings/segments", response_model=List[SegmentStatus])
async def get_segments(
    user_id: int = Depends(get_current_user),
):
    """Get all trading segment statuses (NSE, BSE, NFO, BFO).

    Returns activation status and whether each segment was
    deactivated by the kill switch.
    """
    return _settings_service.get_segments(user_id)


# ---------------------------------------------------------------------------
# PUT /api/v1/settings/segments/{segment}
# ---------------------------------------------------------------------------


@router.put("/settings/segments/{segment}", response_model=SegmentStatus)
async def toggle_segment(
    segment: str,
    body: SegmentToggleRequest,
    user_id: int = Depends(get_current_user),
):
    """Toggle a trading segment's activation status.

    Calls Zerodha API to activate/deactivate the specified segment.

    Path params:
        segment: Segment name (NSE, BSE, NFO, BFO)

    Body:
        activate: True to activate, False to deactivate
    """
    try:
        return _settings_service.toggle_segment(user_id, segment, body.activate)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


# ---------------------------------------------------------------------------
# GET /api/v1/settings/ai
# ---------------------------------------------------------------------------


@router.get("/settings/ai", response_model=AISettings)
async def get_ai_settings(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get AI trading assistant configuration.

    Returns provider info, whether API key is configured,
    and feature toggle states.
    """
    try:
        return _settings_service.get_ai_settings(db, user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ---------------------------------------------------------------------------
# PUT /api/v1/settings/ai
# ---------------------------------------------------------------------------


@router.put("/settings/ai", response_model=AISettings)
async def update_ai_settings(
    settings: AISettingsUpdateRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update AI trading assistant configuration.

    Allows updating provider selection and individual feature toggles.
    Only provided fields are updated.
    """
    # Build dict of only non-None fields for partial update
    update_data = settings.model_dump(exclude_none=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields provided to update",
        )

    try:
        return _settings_service.update_ai_settings(db, user_id, update_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
