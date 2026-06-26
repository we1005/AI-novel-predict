"""Per-book lazy SQLite engine.

The active book (set via ``books.library.set_active(slug)``) determines which
``data/books/<slug>/novel.db`` we connect to. Engines are cached per slug —
switching books doesn't reconnect already-cached ones, just changes which
engine ``session_scope()`` returns.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


_engines: dict[str, tuple[Engine, sessionmaker]] = {}
_LOCK = threading.Lock()

# 进程级/上下文级的「绑定书」覆盖。设置后,get_engine/session_scope **只认它**,
# 无视共享的 data/active_book 指针文件——多进程并发时避免写串库(Phase 5)。
_book_override: ContextVar[str | None] = ContextVar("book_override", default=None)


@contextmanager
def book_scope(slug: str):
    """在此上下文内,所有 DB 操作绑定到 ``slug``,不受其它进程切换 active_book 影响。

    用于跨书串行分析/生成:即便外部(服务/前端)同时把全局 active 切到别的书,
    本上下文的写入仍精确落到 ``slug`` 的 novel.db。
    """
    token = _book_override.set(slug)
    try:
        yield
    finally:
        _book_override.reset(token)


def _configure(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _enable_sqlite_features(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=15000")
        cur.close()


def _build(slug: str) -> tuple[Engine, sessionmaker]:
    from .books.library import book_paths
    p = book_paths(slug)
    p["dir"].mkdir(parents=True, exist_ok=True)
    eng = create_engine(
        f"sqlite:///{p['db_path']}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    _configure(eng)
    SessionLocal = sessionmaker(
        bind=eng, autoflush=False, autocommit=False, expire_on_commit=False,
    )
    # First-time schema init for this book's DB.
    from .memory.schema_init import init_schema
    init_schema(eng)
    return eng, SessionLocal


def _active_slug() -> str:
    override = _book_override.get()
    if override:
        return override
    from .books.library import active_paths, get_active
    slug = get_active()
    if not slug:
        # Calling active_paths picks the first available book or raises.
        active_paths()
        slug = get_active()
    return slug or "__none__"


def get_engine() -> Engine:
    slug = _active_slug()
    with _LOCK:
        cached = _engines.get(slug)
        if cached is not None:
            return cached[0]
        eng, sess = _build(slug)
        _engines[slug] = (eng, sess)
        return eng


def _get_session_factory() -> sessionmaker:
    slug = _active_slug()
    with _LOCK:
        cached = _engines.get(slug)
    if cached is None:
        get_engine()  # builds + caches
        with _LOCK:
            cached = _engines[slug]
    return cached[1]


def _invalidate_engine_cache() -> None:
    """Drop all cached engines (e.g. after switching active book or deleting)."""
    with _LOCK:
        for slug, (eng, _) in list(_engines.items()):
            try:
                eng.dispose()
            except Exception:
                pass
        _engines.clear()


@contextmanager
def session_scope():
    Sess = _get_session_factory()
    s: Session = Sess()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# Backward-compat: legacy code does ``from .db import engine``.
def __getattr__(name: str) -> Any:
    if name == "engine":
        return get_engine()
    if name == "SessionLocal":
        return _get_session_factory()
    raise AttributeError(name)
