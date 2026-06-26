"""项目(project)聚合层:一个 project = 一组成员书 + 意图 + (后续)融合产物。

存独立 project.db(novel-analysis-imitate/backend/data/projects/projects.db),
与现有 per-book novel.db 解耦;成员书的原始抽取仍复用现有 backend/data/books/<slug>/。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

_DATA = Path(__file__).resolve().parents[2] / "data" / "projects"
_DATA.mkdir(parents=True, exist_ok=True)
_DB = _DATA / "projects.db"
_engine = create_engine(f"sqlite:///{_DB}", future=True)


def init() -> None:
    with _engine.begin() as c:
        c.execute(text("""CREATE TABLE IF NOT EXISTS projects(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE, name TEXT, intent TEXT, use_case TEXT,
            member_book_slugs_json TEXT, created_at TEXT)"""))


def create_project(slug: str, name: str, intent: str = "", use_case: str = "",
                   member_book_slugs: list[str] | None = None) -> dict:
    init()
    with _engine.begin() as c:
        c.execute(text("""INSERT OR REPLACE INTO projects
            (slug,name,intent,use_case,member_book_slugs_json,created_at)
            VALUES (:s,:n,:i,:u,:m,:t)"""),
            {"s": slug, "n": name, "i": intent, "u": use_case,
             "m": json.dumps(member_book_slugs or [], ensure_ascii=False),
             "t": datetime.now(timezone.utc).isoformat()})
    return get_project(slug)


def get_project(slug: str) -> dict | None:
    init()
    with _engine.begin() as c:
        r = c.execute(text("SELECT slug,name,intent,use_case,member_book_slugs_json,created_at "
                           "FROM projects WHERE slug=:s"), {"s": slug}).mappings().first()
    if not r:
        return None
    d = dict(r)
    d["member_book_slugs"] = json.loads(d.pop("member_book_slugs_json") or "[]")
    return d


def list_projects() -> list[dict]:
    init()
    with _engine.begin() as c:
        rows = c.execute(text("SELECT slug,name,use_case,member_book_slugs_json,created_at "
                              "FROM projects ORDER BY id DESC")).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["member_book_slugs"] = json.loads(d.pop("member_book_slugs_json") or "[]")
        out.append(d)
    return out
