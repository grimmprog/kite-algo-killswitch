"""User Management API endpoints for the Admin Testing UI.

Provides CRUD operations on the User model via SQLAlchemy session.

Requirements covered:
- 3.1-3.7: User management panel functionality
- 9.4: GET /admin/api/users
- 9.5: POST, PUT, DELETE /admin/api/users
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from src.admin.dependencies import get_db
from src.auth.password import hash_password
from src.database.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Pydantic Models ---


class UserCreateRequest(BaseModel):
    """Request body for creating a new user."""

    email: EmailStr
    password: str
    capital: float = 100000.0
    risk_profile: str = "moderate"
    daily_loss_limit_percent: float = 2.0

    @field_validator("capital")
    @classmethod
    def capital_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Capital must be positive")
        return v

    @field_validator("risk_profile")
    @classmethod
    def risk_profile_must_be_valid(cls, v: str) -> str:
        allowed = ("conservative", "moderate", "aggressive")
        if v not in allowed:
            raise ValueError(
                f"Risk profile must be one of: {', '.join(allowed)}. Got: {v}"
            )
        return v

    @field_validator("daily_loss_limit_percent")
    @classmethod
    def daily_loss_limit_must_be_in_range(cls, v: float) -> float:
        if v < 0.5 or v > 10.0:
            raise ValueError(
                "Daily loss limit percent must be between 0.5 and 10.0"
            )
        return v


class UserUpdateRequest(BaseModel):
    """Request body for updating an existing user."""

    capital: Optional[float] = None
    risk_profile: Optional[str] = None
    daily_loss_limit_percent: Optional[float] = None

    @field_validator("capital")
    @classmethod
    def capital_must_be_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("Capital must be positive")
        return v

    @field_validator("risk_profile")
    @classmethod
    def risk_profile_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed = ("conservative", "moderate", "aggressive")
            if v not in allowed:
                raise ValueError(
                    f"Risk profile must be one of: {', '.join(allowed)}. Got: {v}"
                )
        return v

    @field_validator("daily_loss_limit_percent")
    @classmethod
    def daily_loss_limit_must_be_in_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.5 or v > 10.0):
            raise ValueError(
                "Daily loss limit percent must be between 0.5 and 10.0"
            )
        return v


class UserResponse(BaseModel):
    """Response model for user data."""

    id: int
    email: str
    capital: float
    risk_profile: str
    daily_loss_limit_percent: float
    killswitch_state: bool
    is_active: bool

    model_config = {"from_attributes": True}


# --- Endpoints ---


@router.get("/api/users", response_model=List[UserResponse])
async def list_users(db: Session = Depends(get_db)) -> List[UserResponse]:
    """List all users.

    Returns:
        List of all user records.
    """
    try:
        users = db.query(User).all()
        return [UserResponse.model_validate(u) for u in users]
    except Exception as e:
        logger.error("Failed to list users: %s", e)
        raise HTTPException(status_code=500, detail="Database unavailable")


@router.post("/api/users", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreateRequest,
    db: Session = Depends(get_db),
) -> UserResponse:
    """Create a new user.

    Hashes password via bcrypt and stores the user record.

    Returns:
        The created user record.
    """
    try:
        password_hash = hash_password(body.password)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        user = User(
            email=body.email,
            password_hash=password_hash,
            capital=body.capital,
            risk_profile=body.risk_profile,
            daily_loss_limit_percent=body.daily_loss_limit_percent,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return UserResponse.model_validate(user)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error("Failed to create user: %s", e)
        raise HTTPException(status_code=500, detail="Database unavailable")


@router.put("/api/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    db: Session = Depends(get_db),
) -> UserResponse:
    """Update an existing user.

    Only provided fields are updated.

    Returns:
        The updated user record.
    """
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if body.capital is not None:
            user.capital = body.capital
        if body.risk_profile is not None:
            user.risk_profile = body.risk_profile
        if body.daily_loss_limit_percent is not None:
            user.daily_loss_limit_percent = body.daily_loss_limit_percent

        db.commit()
        db.refresh(user)
        return UserResponse.model_validate(user)
    except HTTPException:
        raise
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error("Failed to update user %d: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Database unavailable")


@router.delete("/api/users/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
) -> None:
    """Delete a user by ID.

    Returns:
        204 No Content on success.
    """
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        db.delete(user)
        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Failed to delete user %d: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Database unavailable")
