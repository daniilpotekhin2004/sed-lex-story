"""
Script to create an admin user.
Usage: python -m scripts.create_admin
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.domain.models import User, UserRole

settings = get_settings()


async def create_admin():
    """Create an admin user."""
    engine = create_async_engine(settings.database_url, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Check if admin exists
        from sqlalchemy import select
        result = await session.execute(
            select(User).where(User.username == "admin")
        )
        existing_admin = result.scalar_one_or_none()

        if existing_admin:
            print("❌ Admin user already exists!")
            return

        # Create admin
        admin = User(
            username="admin",
            email="admin@lexquest.local",
            hashed_password=get_password_hash("admin123"),
            role=UserRole.ADMIN,
            is_active=True,
            full_name="System Administrator",
        )

        session.add(admin)
        await session.commit()
        await session.refresh(admin)

        print("✅ Admin user created successfully!")
        print(f"   Username: admin")
        print(f"   Password: admin123")
        print(f"   Email: admin@lexquest.local")
        print(f"   ID: {admin.id}")
        print("\n⚠️  Please change the password after first login!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_admin())
