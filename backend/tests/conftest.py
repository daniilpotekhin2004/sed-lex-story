import asyncio
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("SD_MOCK_MODE", "true")
os.environ.setdefault("ASSETS_ROOT", "assets")
os.environ.setdefault("GENERATED_ASSETS_SUBDIR", "generated")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.infra.db import engine, init_db
from app.domain.models import User, UserRole
from app.infra.db import SessionLocal
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def prepare_database():
    await init_db()
    yield
    await engine.dispose()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth_session(client: TestClient):
    def _create(
        username: str | None = None,
        *,
        role: str = "player",
        cohort_code: str | None = None,
        password: str = "password123",
        full_name: str | None = None,
    ) -> dict:
        actual_username = username or f"user-{uuid.uuid4().hex[:8]}"
        register_response = client.post(
            "/api/auth/register",
            json={
                "username": actual_username,
                "email": f"{actual_username}@example.com",
                "password": password,
                "full_name": full_name,
            },
        )
        assert register_response.status_code == 201
        registered_user = register_response.json()

        async def _update_user() -> None:
            async with SessionLocal() as session:
                result = await session.execute(select(User).where(User.id == registered_user["id"]))
                user = result.scalar_one()
                user.role = UserRole(role.lower())
                user.cohort_code = cohort_code.strip().upper() if cohort_code else None
                await session.commit()

        asyncio.get_event_loop().run_until_complete(_update_user())

        login_response = client.post(
            "/api/auth/login",
            json={
                "username": actual_username,
                "password": password,
            },
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        return {
            "id": registered_user["id"],
            "username": actual_username,
            "role": role.lower(),
            "cohort_code": cohort_code.strip().upper() if cohort_code else None,
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"},
        }

    return _create
