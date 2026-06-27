"""Multi-book library: register / import / switch between novels.

Layout
------
    backend/data/
    ├── settings.json         (global — model picks, API key, etc.)
    ├── active_book           (single line; the slug of the currently selected book)
    ├── library/              (drop *.txt files here for import)
    └── books/                (one subfolder per imported book)
        └── <slug>/
            ├── corpus.txt    (utf-8 normalized full text)
            ├── novel.db      (per-book SQLite)
            ├── novel.db-wal
            └── chroma/       (per-book vector store)

Auto-migration
--------------
On first call to ``ensure_layout()``, if ``data/novel.db`` exists but
``data/books/`` is empty, the legacy data is moved into a new book folder
inferred from the corpus filename (default 末法王座). One-shot, idempotent.
"""

from __future__ import annotations

import re
import shutil
import threading
from pathlib import Path
from typing import Any

from ..config import DATA_DIR

LIBRARY_DIR = DATA_DIR / "library"
BOOKS_DIR = DATA_DIR / "books"
ACTIVE_FILE = DATA_DIR / "active_book"

LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
BOOKS_DIR.mkdir(parents=True, exist_ok=True)

_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Slug + paths
# ---------------------------------------------------------------------------


def _slug(name: str) -> str:
    """Filesystem-safe slug. CJK characters are preserved."""
    s = name.strip()
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s)
    s = re.sub(r"\s+", "_", s)
    s = s.strip(" .")
    return s or "untitled"


def book_dir(slug: str) -> Path:
    return BOOKS_DIR / slug


def book_paths(slug: str) -> dict[str, Path]:
    d = book_dir(slug)
    return {
        "dir": d,
        "corpus_txt": d / "corpus.txt",
        "db_path": d / "novel.db",
        "chroma_dir": d / "chroma",
    }


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def list_library_files() -> list[dict[str, Any]]:
    """Raw .txt files in data/library/ awaiting import."""
    out: list[dict[str, Any]] = []
    if not LIBRARY_DIR.exists():
        return out
    imported_slugs = {b["slug"] for b in list_books()}
    for f in sorted(LIBRARY_DIR.glob("*.txt")):
        slug = _slug(f.stem)
        out.append({
            "filename": f.name,
            "stem": f.stem,
            "size": f.stat().st_size,
            "suggested_slug": slug,
            "already_imported": slug in imported_slugs,
        })
    return out


def list_books() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not BOOKS_DIR.exists():
        return out
    active = get_active()
    for d in sorted(BOOKS_DIR.iterdir()):
        if not d.is_dir():
            continue
        p = book_paths(d.name)
        out.append({
            "slug": d.name,
            "title": d.name,
            "active": d.name == active,
            "has_corpus": p["corpus_txt"].exists(),
            "has_db": p["db_path"].exists(),
            "corpus_bytes": p["corpus_txt"].stat().st_size if p["corpus_txt"].exists() else 0,
            "db_bytes": p["db_path"].stat().st_size if p["db_path"].exists() else 0,
        })
    return out


# ---------------------------------------------------------------------------
# Active book
# ---------------------------------------------------------------------------


def get_active() -> str | None:
    if not ACTIVE_FILE.exists():
        return None
    s = ACTIVE_FILE.read_text(encoding="utf-8").strip()
    return s or None


def set_active(slug: str) -> None:
    if not (BOOKS_DIR / slug).is_dir():
        raise ValueError(f"book {slug!r} not found")
    with _LOCK:
        ACTIVE_FILE.write_text(slug, encoding="utf-8")
    # Tell db.py to drop its cached engine — next session_scope() will rebuild
    # against the new book's DB.
    try:
        from .. import db as _db
        _db._invalidate_engine_cache()  # type: ignore[attr-defined]
    except Exception:
        pass


def active_paths() -> dict[str, Path]:
    """Get paths for the active book. Auto-pick first available if none set.
    Raises only if no books exist at all."""
    slug = get_active()
    if not slug or not (BOOKS_DIR / slug).is_dir():
        books = [d.name for d in BOOKS_DIR.iterdir() if d.is_dir()] if BOOKS_DIR.exists() else []
        if not books:
            raise RuntimeError(
                "no books imported yet — drop a .txt into data/library/ "
                "and POST /books/import"
            )
        slug = sorted(books)[0]
        ACTIVE_FILE.write_text(slug, encoding="utf-8")
    return book_paths(slug)


# ---------------------------------------------------------------------------
# Import / delete
# ---------------------------------------------------------------------------


def import_from_library(filename: str, *, title: str | None = None) -> dict[str, Any]:
    """Decode a .txt in data/library/ and create a new book folder.

    Doesn't run chapter splitting — caller does that explicitly via
    ``POST /ingest/split`` after switching to the new book.
    """
    src = LIBRARY_DIR / filename
    if not src.exists():
        raise FileNotFoundError(f"{filename!r} not in {LIBRARY_DIR}")

    slug = _slug(title or src.stem)
    dest_dir = book_dir(slug)
    if dest_dir.exists():
        raise ValueError(f"book {slug!r} already exists")

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Decode using the existing chardet pipeline.
    from ..ingest.split import detect_and_load
    body = detect_and_load(src)
    book_paths(slug)["corpus_txt"].write_text(body, encoding="utf-8")

    return {
        "slug": slug,
        "title": title or src.stem,
        "size": len(body),
        "active_after_import": False,
    }


def delete_book(slug: str) -> None:
    # 修复 G4(红蓝对抗):active 检查与 rmtree 放进 _LOCK 原子化,防并发 set_active 在
    # "检查通过"与"删除"之间切走指针,误删一本"判定时还是 active"的书(TOCTOU 不可逆销毁)。
    with _LOCK:
        if get_active() == slug:
            raise ValueError("cannot delete active book — switch first")
        d = book_dir(slug)
        if not d.exists():
            return
        # Drop any cached engines that might still hold sqlite file handles.
        try:
            from .. import db as _db
            _db._invalidate_engine_cache()  # type: ignore[attr-defined]
        except Exception:
            pass
        shutil.rmtree(d)


# ---------------------------------------------------------------------------
# Auto-migration (legacy → books/<slug>/)
# ---------------------------------------------------------------------------


def ensure_layout() -> None:
    """One-time migration. Called at app startup.

    If ``data/novel.db`` exists and ``data/books/`` is empty, move legacy
    files into a new book folder. Idempotent — on subsequent calls does
    nothing.
    """
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

    if any(BOOKS_DIR.iterdir()):
        return  # already migrated

    legacy_db = DATA_DIR / "novel.db"
    if not legacy_db.exists():
        return  # nothing to migrate

    # Infer book title from corpus/<NAME>.utf8.txt if present.
    legacy_corpus = DATA_DIR / "corpus"
    title: str | None = None
    if legacy_corpus.exists():
        for f in legacy_corpus.glob("*.utf8.txt"):
            title = f.stem.removesuffix(".utf8")
            break
    title = title or "默认书"
    slug = _slug(title)
    dest = book_dir(slug)
    dest.mkdir(parents=True, exist_ok=True)

    # Move SQLite triple
    for ext in ("", "-wal", "-shm"):
        src = DATA_DIR / f"novel.db{ext}"
        if src.exists():
            shutil.move(str(src), str(dest / f"novel.db{ext}"))

    # Move chroma dir
    if (DATA_DIR / "chroma").exists():
        shutil.move(str(DATA_DIR / "chroma"), str(dest / "chroma"))

    # Move first .utf8.txt as canonical corpus.txt
    if legacy_corpus.exists():
        utf8s = list(legacy_corpus.glob("*.utf8.txt"))
        if utf8s:
            shutil.move(str(utf8s[0]), str(dest / "corpus.txt"))
        # try to clean up empty dir
        try:
            legacy_corpus.rmdir()
        except OSError:
            pass

    ACTIVE_FILE.write_text(slug, encoding="utf-8")
