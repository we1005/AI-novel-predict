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
        # compose 虚拟书:一次生成任务的产物书(复用现有 per-book schema)。
        c.execute(text("""CREATE TABLE IF NOT EXISTS compose_book(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cslug TEXT UNIQUE, project_slug TEXT, use_case TEXT,
            source_slugs_json TEXT, voice_source TEXT,
            outline_run_id INTEGER, meta_json TEXT, created_at TEXT)"""))


def record_compose(cslug: str, *, project_slug: str = "", use_case: str = "",
                   source_slugs: list[str] | None = None, voice_source: str = "",
                   outline_run_id: int | None = None, meta: dict | None = None) -> dict:
    init()
    with _engine.begin() as c:
        c.execute(text("""INSERT OR REPLACE INTO compose_book
            (cslug,project_slug,use_case,source_slugs_json,voice_source,outline_run_id,meta_json,created_at)
            VALUES (:c,:p,:u,:s,:v,:o,:m,:t)"""),
            {"c": cslug, "p": project_slug, "u": use_case,
             "s": json.dumps(source_slugs or [], ensure_ascii=False),
             "v": voice_source, "o": outline_run_id,
             "m": json.dumps(meta or {}, ensure_ascii=False),
             "t": datetime.now(timezone.utc).isoformat()})
    return get_compose(cslug)


def set_compose_outline(cslug: str, outline_run_id: int) -> None:
    init()
    with _engine.begin() as c:
        c.execute(text("UPDATE compose_book SET outline_run_id=:o WHERE cslug=:c"),
                  {"o": outline_run_id, "c": cslug})


def get_compose(cslug: str) -> dict | None:
    init()
    with _engine.begin() as c:
        r = c.execute(text("SELECT * FROM compose_book WHERE cslug=:c"), {"c": cslug}).mappings().first()
    if not r:
        return None
    d = dict(r)
    d["source_slugs"] = json.loads(d.pop("source_slugs_json") or "[]")
    d["meta"] = json.loads(d.pop("meta_json") or "{}")
    return d


def list_compose() -> list[dict]:
    init()
    with _engine.begin() as c:
        rows = c.execute(text("SELECT cslug,project_slug,use_case,source_slugs_json,voice_source,"
                              "outline_run_id,created_at FROM compose_book ORDER BY id DESC")).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["source_slugs"] = json.loads(d.pop("source_slugs_json") or "[]")
        out.append(d)
    return out


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
