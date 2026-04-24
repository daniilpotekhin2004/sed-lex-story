"""
Setup endpoints for initial system configuration.
These endpoints are only accessible when no admin users exist.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.infra.db import get_session as get_db_session
from app.domain.models.user import User, UserRole
from app.core.security import get_password_hash

router = APIRouter(prefix="/setup", tags=["setup"])


class InitialAdminCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6)
    email: str = Field(default="admin@lexquest.local")


@router.post("/create-admin", status_code=status.HTTP_201_CREATED)
async def create_initial_admin(
    data: InitialAdminCreate,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Create initial admin user. Only works if no admin users exist.
    This is a one-time setup endpoint for production deployment.
    """
    # Check if any admin users already exist
    result = await db.execute(
        select(User).where(User.role == UserRole.ADMIN)
    )
    existing_admin = result.scalar_one_or_none()
    
    if existing_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin user already exists. Use normal registration or contact existing admin."
        )
    
    # Create admin user
    admin = User(
        username=data.username,
        email=data.email,
        hashed_password=get_password_hash(data.password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    
    return {
        "message": "Admin user created successfully",
        "username": admin.username,
        "user_id": admin.id,
    }


@router.get("/needs-setup")
async def check_needs_setup(
    db: AsyncSession = Depends(get_db_session),
):
    """
    Check if the system needs initial setup (no admin users exist).
    """
    result = await db.execute(
        select(User).where(User.role == UserRole.ADMIN)
    )
    existing_admin = result.scalar_one_or_none()
    
    return {
        "needs_setup": existing_admin is None,
        "has_admin": existing_admin is not None,
    }
