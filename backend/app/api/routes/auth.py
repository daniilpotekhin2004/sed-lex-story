from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_active_user
from app.infra.db import get_session as get_db_session
from app.schemas.auth import UserRegister, UserLogin, Token, TokenRefresh, UserResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegister,
    db: AsyncSession = Depends(get_db_session),
):
    """Register a new user."""
    auth_service = AuthService(db)
    user = await auth_service.register(data)
    return user


@router.post("/login", response_model=Token)
async def login(
    data: UserLogin,
    db: AsyncSession = Depends(get_db_session),
):
    """Login and get access token."""
    auth_service = AuthService(db)
    return await auth_service.login(data)


@router.post("/refresh", response_model=Token)
async def refresh(
    data: TokenRefresh,
    db: AsyncSession = Depends(get_db_session),
):
    """Refresh access token using refresh token."""
    auth_service = AuthService(db)
    return await auth_service.refresh_token(data.refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user = Depends(get_current_active_user),
):
    """Get current user information."""
    return current_user
