import sqlite3
from pathlib import Path

from app.infra.migrations import apply_pending_migrations


def _create_revision_015_database(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE users (
                id VARCHAR(32) PRIMARY KEY,
                username VARCHAR(64) NOT NULL,
                email VARCHAR(255) NOT NULL,
                hashed_password VARCHAR(255) NOT NULL,
                role VARCHAR(32) NOT NULL,
                is_active BOOLEAN NOT NULL,
                full_name VARCHAR(255),
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE alembic_version (
                version_num VARCHAR(32) NOT NULL
            )
            """
        )
        cur.execute("INSERT INTO alembic_version (version_num) VALUES ('015')")
        conn.commit()
    finally:
        conn.close()


def test_apply_pending_migrations_adds_users_cohort_code(tmp_path: Path) -> None:
    db_path = tmp_path / "migration-test.sqlite3"
    _create_revision_015_database(db_path)

    apply_pending_migrations(f"sqlite+aiosqlite:///{db_path.as_posix()}")

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        column_names = {row[1] for row in cur.fetchall()}
        assert "cohort_code" in column_names

        cur.execute("SELECT version_num FROM alembic_version")
        assert cur.fetchone() == ("018",)
    finally:
        conn.close()
