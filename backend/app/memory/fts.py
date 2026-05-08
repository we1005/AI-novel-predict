"""Wrapper around the chapter_fts virtual table for BM25-flavored recall."""

from __future__ import annotations

from sqlalchemy import text

from ..db import get_engine


def search(query: str, limit: int = 8, before_chapter: int | None = None) -> list[dict]:
    """Return top-k matching chapter snippets, optionally restricted to chapters
    earlier than ``before_chapter`` (so prediction time can't peek at the future)."""

    sql = (
        "SELECT chapter, title, snippet(chapter_fts, 2, '<<', '>>', '…', 32) AS snip, "
        "bm25(chapter_fts) AS score "
        "FROM chapter_fts WHERE chapter_fts MATCH :q "
    )
    params = {"q": query, "n": limit}
    if before_chapter is not None:
        sql += "AND chapter < :before "
        params["before"] = before_chapter
    sql += "ORDER BY score LIMIT :n"

    with get_engine().begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]
