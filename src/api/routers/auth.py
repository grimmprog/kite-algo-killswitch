"""Authentication API endpoints.

Requirements covered:
- 1.1.4: JWT-based authentication with 24-hour access token expiry
- 1.1.5: Refresh tokens with 30-day expiry
- 1.1.10: Support user logout and token invalidation
- 1.2.2: Support OAuth-based broker authentication
- 1.2.3: Encrypt broker access tokens before storing in database

Endpoints:
- POST /api/v1/auth/login — Authenticate user, return JWT tokens
- POST /api/v1/auth/refresh — Refresh access token using refresh token
- POST /api/v1/auth/logout — Invalidate current session
- POST /api/v1/auth/broker-connect — Connect broker via OAuth callback
"""

import os
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, get_current_user
from src.api.schemas import LoginRequest, TokenResponse, RefreshRequest
from src.auth.exceptions import AuthenticationError
from src.auth.jwt_handler import JWTHandler
from src.auth.service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-key")


# --------------------------------------------------------------------------
# Request models specific to this router
# --------------------------------------------------------------------------


class BrokerConnectRequest(BaseModel):
    """Request body for broker OAuth callback."""

    request_token: str


# --------------------------------------------------------------------------
# 9.1: POST /api/v1/auth/login
# --------------------------------------------------------------------------


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user and return JWT tokens.

    9.1.1: Validate credentials
    9.1.2: Generate JWT tokens (access + refresh)
    9.1.3: Return tokens in response
    9.1.4: Handle invalid credentials with 401
    """
    jwt_handler = JWTHandler(secret_key=JWT_SECRET_KEY)
    auth_service = AuthService(jwt_handler=jwt_handler, db_session=db)

    try:
        result = auth_service.authenticate_user(request.email, request.password)
        return result
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


# --------------------------------------------------------------------------
# 9.2: POST /api/v1/auth/refresh
# --------------------------------------------------------------------------


@router.post("/refresh")
async def refresh_token(request: RefreshRequest, db: Session = Depends(get_db)):
    """Refresh access token using a valid refresh token.

    9.2.1: Validate refresh token
    9.2.2: Generate new access token
    9.2.3: Return new token in response
    """
    jwt_handler = JWTHandler(secret_key=JWT_SECRET_KEY)
    auth_service = AuthService(jwt_handler=jwt_handler, db_session=db)

    try:
        result = auth_service.refresh_access_token(request.refresh_token)
        return result
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


# --------------------------------------------------------------------------
# 9.3: POST /api/v1/auth/logout
# --------------------------------------------------------------------------


@router.post("/logout")
async def logout(
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Logout current user and invalidate session.

    9.3.1: Invalidate tokens (record logout)
    9.3.2: Return success response
    """
    jwt_handler = JWTHandler(secret_key=JWT_SECRET_KEY)
    auth_service = AuthService(jwt_handler=jwt_handler, db_session=db)
    auth_service.logout(user_id)
    return {"message": "Logged out successfully"}


# --------------------------------------------------------------------------
# 9.4: POST /api/v1/auth/broker-connect
# --------------------------------------------------------------------------


@router.post("/broker-connect")
async def broker_connect(
    request: BrokerConnectRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Connect broker account via OAuth callback token.

    9.4.1: Handle OAuth callback (exchange request_token for access_token)
    9.4.2: Store encrypted tokens in database
    9.4.3: Return success response
    """
    from src.broker.oauth import ZerodhaOAuth, OAuthError
    from src.broker.token_encryption import TokenEncryption

    # Load broker config from environment
    api_key = os.environ.get("KITE_API_KEY", "")
    api_secret = os.environ.get("KITE_API_SECRET", "")
    redirect_url = os.environ.get("KITE_REDIRECT_URL", "http://localhost:8000/callback")
    encryption_key = os.environ.get("ENCRYPTION_KEY", "")

    if not api_key or not api_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Broker API credentials not configured",
        )

    if not encryption_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Encryption key not configured",
        )

    try:
        oauth = ZerodhaOAuth(
            api_key=api_key,
            api_secret=api_secret,
            redirect_url=redirect_url,
        )
        encryptor = TokenEncryption(encryption_key=encryption_key)

        # Exchange request token for access token
        token_data = oauth.handle_callback(request.request_token)

        # Store encrypted tokens in database
        oauth.store_tokens(
            user_id=user_id,
            access_token=token_data["access_token"],
            db_session=db,
            encryptor=encryptor,
            public_token=token_data.get("public_token"),
        )

        return {"message": "Broker connected successfully"}

    except OAuthError as e:
        logger.error(f"Broker connection failed for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Broker connection failed: {str(e)}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
