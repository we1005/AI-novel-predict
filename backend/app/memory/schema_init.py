"""Initialize SQLite schema, including FTS5 virtual table for raw chapter text."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .models import Base


FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chapter_fts USING fts5(
    chapter UNINDEXED,
    title,
    body,
    tokenize = 'trigram'
);
"""


def init_schema(engine: Engine | None = None) -> None:
    """Create tables + lightweight column migrations.

    Pass an explicit ``engine`` for a non-default book; if omitted we resolve
    the active book's engine at call time.
    """
    if engine is None:
        from ..db import get_engine
        engine = get_engine()
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(FTS_DDL))
        # Column migrations. SQLAlchemy ``create_all`` only adds missing tables.
        _ensure_column(conn, "arc_runs", "user_hints", "TEXT")
        _ensure_column(conn, "mysteries", "status", "TEXT DEFAULT 'open'")
        _ensure_column(conn, "mysteries", "confidence", "INTEGER DEFAULT 50")
        _ensure_column(conn, "mysteries", "first_seen_batch_id", "INTEGER")
        _ensure_column(conn, "mysteries", "last_updated_batch_id", "INTEGER")
        _ensure_column(conn, "mysteries", "last_updated_chapter", "INTEGER")
        _ensure_column(conn, "mysteries", "updates_log_json", "TEXT")
        _ensure_column(conn, "entities", "role", "TEXT")
        _ensure_column(conn, "bilingual_draft", "stage", "TEXT DEFAULT ''")


def _ensure_column(conn, table: str, col: str, decl: str) -> None:
    cols = [r[1] for r in conn.execute(text(f"PRAGMA table_info({table})"))]
    if col not in cols:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {decl}"))


if __name__ == "__main__":
    init_schema()
    print("schema initialized")
