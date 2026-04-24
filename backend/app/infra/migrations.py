from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import Lock

from alembic import command
from alembic.config import Config
from sqlalchemy.engine.url import make_url


BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = BACKEND_DIR / "alembic.ini"
ALEMBIC_SCRIPT_PATH = BACKEND_DIR / "alembic_migrations"

_MIGRATION_LOCK = Lock()


def is_ephemeral_database(database_url: str) -> bool:
    try:
        url = make_url(database_url)
    except Exception:
        return False

    return url.get_backend_name() == "sqlite" and url.database == ":memory:"


def _resolve_sqlite_database_path(database_url: str) -> Path | None:
    try:
        url = make_url(database_url)
    except Exception:
        return None

    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None

    path = Path(url.database)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _ensure_sqlite_user_preset_columns(database_url: str) -> None:
    path = _resolve_sqlite_database_path(database_url)
    if path is None or not path.exists():
        return

    conn = sqlite3.connect(str(path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_generation_presets'")
        if cur.fetchone() is None:
            return

        cur.execute("PRAGMA table_info(user_generation_presets)")
        existing = {row[1] for row in cur.fetchall()}
        columns = {
            "scheduler": "TEXT",
            "model_id": "TEXT",
            "vae_id": "TEXT",
            "seed": "INTEGER",
            "pipeline_profile_id": "TEXT",
            "pipeline_profile_version": "INTEGER",
        }
        for name, col_type in columns.items():
            if name not in existing:
                cur.execute(f"ALTER TABLE user_generation_presets ADD COLUMN {name} {col_type}")
        conn.commit()
    finally:
        conn.close()


def apply_pending_migrations(database_url: str) -> None:
    if is_ephemeral_database(database_url):
        return

    with _MIGRATION_LOCK:
        _ensure_sqlite_user_preset_columns(database_url)

        alembic_cfg = Config(str(ALEMBIC_INI_PATH))
        alembic_cfg.set_main_option("script_location", str(ALEMBIC_SCRIPT_PATH))
        alembic_cfg.set_main_option("sqlalchemy.url", database_url)
        command.upgrade(alembic_cfg, "head")
