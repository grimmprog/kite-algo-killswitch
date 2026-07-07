"""Broker Settings API endpoints.

Requirements covered:
- 8.1: GET /api/v1/settings/brokers/kite — Kite connection status (no raw tokens)
- 8.2: POST /api/v1/settings/brokers/kite/reconnect — Initiate OAuth, return login URL
- 8.3: PUT /api/v1/settings/brokers/kite/auto-login — Update TOTP key + enabled flag
- 8.9: All endpoints require authentication

Endpoints:
- GET  /api/v1/settings/brokers/kite            — Get Kite connection status
- POST /api/v1/settings/brokers/kite/reconnect  — Initiate OAuth reconnection
- GET  /api/v1/settings/brokers/kite/callback   — Handle OAuth callback
- PUT  /api/v1/settings/brokers/kite/auto-login — Update auto-login configuration
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user, get_db
from src.broker.oauth import OAuthError
from src.broker.token_encryption import TokenEncryption
from src.services.broker_settings_service import BrokerSettingsService, KiteStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings/brokers", tags=["broker-settings"])


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class AutoLoginRequest(BaseModel):
    """Request body for updating auto-login configuration."""

    totp_key: Optional[str] = None
    enabled: bool


# ---------------------------------------------------------------------------
# Service factory
# ---------------------------------------------------------------------------


def _get_broker_settings_service() -> BrokerSettingsService:
    """Create a BrokerSettingsService instance with environment-based encryption key.

    Returns:
        A configured BrokerSettingsService instance.

    Raises:
        HTTPException: If the encryption key is not configured.
    """
    encryption_key = os.environ.get("ENCRYPTION_KEY", "")
    if not encryption_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Encryption key not configured",
        )
    token_encryption = TokenEncryption(encryption_key=encryption_key)
    return BrokerSettingsService(token_encryption=token_encryption)


# ---------------------------------------------------------------------------
# GET /api/v1/settings/brokers/kite
# ---------------------------------------------------------------------------


@router.get("/kite", response_model=KiteStatusResponse)
async def get_kite_status(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get Kite connection status for the authenticated user.

    Returns the derived connection status (Connected/Disconnected/Token Expired),
    token expiry timestamp, time remaining, and auto-login metadata.
    Never includes raw access tokens or TOTP keys.

    Requirement 8.1: Returns status excluding sensitive token values.
    Requirement 8.9: Requires authentication.
    """
    service = _get_broker_settings_service()
    return service.get_kite_status(db, user_id)


# ---------------------------------------------------------------------------
# POST /api/v1/settings/brokers/kite/reconnect
# ---------------------------------------------------------------------------


@router.post("/kite/reconnect")
async def initiate_kite_reconnect(
    user_id: int = Depends(get_current_user),
):
    """Initiate Kite OAuth reconnection flow.

    Returns the Zerodha login URL. The frontend should redirect the user
    to this URL to complete the OAuth authentication.

    Requirement 8.2: Initiates OAuth flow, returns login redirect URL.
    Requirement 8.9: Requires authentication.
    """
    service = _get_broker_settings_service()

    try:
        login_url = service.initiate_reconnect(user_id)
        return {"login_url": login_url}
    except RuntimeError as e:
        logger.error("Reconnect failed for user %d: %s", user_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# ---------------------------------------------------------------------------
# GET /api/v1/settings/brokers/kite/callback
# ---------------------------------------------------------------------------


@router.get("/kite/callback", response_model=KiteStatusResponse)
async def handle_kite_callback(
    request_token: str = Query(..., description="OAuth request token from Zerodha"),
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Handle the Kite OAuth callback after user authenticates with Zerodha.

    Exchanges the request_token for an access token, encrypts and stores it,
    then returns the updated connection status.

    Requirement 8.2: Handles OAuth callback flow.
    Requirement 8.9: Requires authentication.
    """
    service = _get_broker_settings_service()

    try:
        service.handle_oauth_callback(db, user_id, request_token)
    except OAuthError as e:
        logger.error("OAuth callback failed for user %d: %s", user_id, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth flow cancelled or failed: {str(e)}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    # Return updated status after successful token exchange
    return service.get_kite_status(db, user_id)


# ---------------------------------------------------------------------------
# PUT /api/v1/settings/brokers/kite/auto-login
# ---------------------------------------------------------------------------


@router.put("/kite/auto-login")
async def update_auto_login(
    body: AutoLoginRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update Kite auto-login configuration.

    Accepts a TOTP key (optional — pass None to keep existing) and an
    enabled flag. Validates the TOTP key if provided, encrypts it, and
    stores the configuration.

    Requirement 8.3: Accepts TOTP key and enabled status, validates,
    encrypts, and stores configuration.
    Requirement 8.9: Requires authentication.
    """
    service = _get_broker_settings_service()

    try:
        service.update_auto_login(db, user_id, body.totp_key, body.enabled)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


# ---------------------------------------------------------------------------
# Dhan endpoints
# ---------------------------------------------------------------------------


class DhanConnectRequest(BaseModel):
    """Request body for Dhan broker connection."""

    client_id: str
    access_token: str


@router.get("/dhan")
async def get_dhan_status(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get Dhan connection status for the authenticated user.

    Returns connection status and account name. No raw token
    or client ID values are exposed in the response.
    """
    service = _get_broker_settings_service()
    return service.get_dhan_status(db, user_id)


@router.post("/dhan/connect")
async def connect_dhan(
    request: DhanConnectRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Connect Dhan broker with provided credentials.

    Validates credentials by initializing a DhanHQ client and verifying
    connectivity. On success, encrypts and stores credentials.
    """
    service = _get_broker_settings_service()
    try:
        service.connect_dhan(db, user_id, request.client_id, request.access_token)
        return service.get_dhan_status(db, user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except ConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.delete("/dhan/connect")
async def disconnect_dhan(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Disconnect Dhan broker and remove all stored credentials."""
    service = _get_broker_settings_service()
    service.disconnect_dhan(db, user_id)
    return {"success": True}
