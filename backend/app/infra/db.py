from __future__ import annotations

import asyncio
import os
from pathlib import Path
from tempfile import gettempdir
from typing import AsyncGenerator

from sqlalchemy import create_engine, inspect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.domain.models.base import Base
from app.infra.migrations import apply_pending_migrations, is_ephemeral_database

settings = get_settings()
database_url = settings.database_url
startup_database_url = database_url

engine_kwargs = {"echo": False, "future": True}
if is_ephemeral_database(database_url):
    shared_test_db = Path(gettempdir()) / f"lwq-test-{os.getpid()}.sqlite3"
    shared_test_db.unlink(missing_ok=True)
    database_url = f"sqlite+aiosqlite:///{shared_test_db.as_posix()}"
    engine_kwargs["poolclass"] = StaticPool
    engine_kwargs["connect_args"] = {"check_same_thread": False}
elif database_url.startswith("sqlite+aiosqlite"):
    engine_kwargs["poolclass"] = StaticPool
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine: AsyncEngine = create_async_engine(database_url, **engine_kwargs)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Sync engine and session for Celery workers
sync_db_url = database_url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")
sync_engine_kwargs = {"echo": False, "future": True}
if sync_db_url.startswith("sqlite"):
    sync_engine_kwargs["connect_args"] = {"check_same_thread": False}
sync_engine = create_engine(sync_db_url, **sync_engine_kwargs)
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    # Ensure models are imported before creating tables
    import app.domain.models  # noqa: F401

    if not is_ephemeral_database(startup_database_url):
        await asyncio.to_thread(apply_pending_migrations, database_url)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_archive_columns)


def _ensure_archive_columns(sync_conn) -> None:
    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    archive_tables = (
        "projects",
        "scenario_graphs",
        "character_presets",
        "locations",
        "artifacts",
        "document_templates",
    )

    for table_name in archive_tables:
        if table_name not in existing_tables:
            continue
        column_names = {column["name"] for column in inspector.get_columns(table_name)}
        if "archived_at" in column_names:
            continue
        if sync_conn.dialect.name == "postgresql":
            sync_conn.exec_driver_sql(
                f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP NULL"
            )
        else:
            sync_conn.exec_driver_sql(
                f"ALTER TABLE {table_name} ADD COLUMN archived_at TIMESTAMP NULL"
            )
