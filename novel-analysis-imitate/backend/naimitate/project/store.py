"""项目(project)聚合层:一个 project = 一组成员书 + 意图 + (后续)融合产物。

存独立 project.db(novel-analysis-imitate/backend/data/projects/projects.db),
与现有 per-book novel.db 解耦;成员书的原始抽取仍复用现有 backend/data/books/<slug>/。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text, event

_DATA = Path(__file__).resolve().parents[2] / "data" / "projects"
_DATA.mkdir(parents=True, exist_ok=True)
_DB = _DATA / "projects.db"
_engine = create_engine(f"sqlite:///{_DB}", future=True)


# 修复 F1(红蓝对抗):墨笔 db.py 给 per-book 库挂了 WAL+busy_timeout+FK,墨析项目库漏了,
# 并发融合写入撞 SQLITE_BUSY 会静默丢产物。补齐同款 PRAGMA。
@event.listens_for(_engine, "connect")
def _enable_sqlite_features(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=15000")
    cur.close()


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
        # Phase 3 跨书融合产物(导演手册)。一个 project 各一行,kind 区分。
        c.execute(text("""CREATE TABLE IF NOT EXISTS fused_product(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_slug TEXT, kind TEXT,
            card_json TEXT, source_slugs_json TEXT, cost_usd REAL, updated_at TEXT,
            UNIQUE(project_slug, kind))"""))
        # 通用类型模板(genre_template):从一组**同题材**书的语义层抽出、可保存可调用的"写作配方"。
        # V_genre 验证:语义模板 > 裸prompt(三轴全胜)、≥ 贴单作者;纯语义(结构指纹归作者层,V1)。
        # template_json: {imagery, motifs, worldview_lexicon, atmosphere, flavor_recipe, anti_patterns}
        # system_prompt: 渲染好的、可直接喂 writer 的指令(含 V2 求异/留白护栏)。
        c.execute(text("""CREATE TABLE IF NOT EXISTS genre_template(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE, name TEXT, source_slugs_json TEXT,
            template_json TEXT, system_prompt TEXT, cost_usd REAL,
            created_at TEXT, updated_at TEXT)"""))
        # 通用 kv 配置(如 genre 抽样策略默认值)。
        c.execute(text("""CREATE TABLE IF NOT EXISTS app_config(
            key TEXT PRIMARY KEY, value_json TEXT, updated_at TEXT)"""))


def save_fused(project_slug: str, kind: str, card: dict, *,
               source_slugs: list[str] | None = None, cost_usd: float = 0.0) -> dict:
    """kind: fused_worldview / fused_style / fused_technique。"""
    init()
    with _engine.begin() as c:
        c.execute(text("""INSERT OR REPLACE INTO fused_product
            (project_slug,kind,card_json,source_slugs_json,cost_usd,updated_at)
            VALUES (:p,:k,:c,:s,:cost,:t)"""),
            {"p": project_slug, "k": kind,
             "c": json.dumps(card, ensure_ascii=False),
             "s": json.dumps(source_slugs or [], ensure_ascii=False),
             "cost": cost_usd, "t": datetime.now(timezone.utc).isoformat()})
    return get_fused(project_slug, kind)


def get_fused(project_slug: str, kind: str) -> dict | None:
    init()
    with _engine.begin() as c:
        r = c.execute(text("SELECT * FROM fused_product WHERE project_slug=:p AND kind=:k"),
                      {"p": project_slug, "k": kind}).mappings().first()
    if not r:
        return None
    d = dict(r)
    d["card"] = json.loads(d.pop("card_json") or "{}")
    d["source_slugs"] = json.loads(d.pop("source_slugs_json") or "[]")
    return d


def list_fused(project_slug: str) -> dict:
    init()
    with _engine.begin() as c:
        rows = c.execute(text("SELECT kind,source_slugs_json,updated_at FROM fused_product "
                              "WHERE project_slug=:p"), {"p": project_slug}).mappings().all()
    out = {}
    for r in rows:
        out[r["kind"]] = {"source_slugs": json.loads(r["source_slugs_json"] or "[]"),
                          "updated_at": r["updated_at"]}
    return out


# ---------------------------------------------------------------------------
# genre_template:通用类型模板(可保存/可调用)
# ---------------------------------------------------------------------------

def save_genre_template(slug: str, name: str, *, template: dict, system_prompt: str,
                        source_slugs: list[str] | None = None, cost_usd: float = 0.0) -> dict:
    init()
    now = datetime.now(timezone.utc).isoformat()
    with _engine.begin() as c:
        exists = c.execute(text("SELECT created_at FROM genre_template WHERE slug=:s"),
                           {"s": slug}).scalar()
        c.execute(text("""INSERT OR REPLACE INTO genre_template
            (slug,name,source_slugs_json,template_json,system_prompt,cost_usd,created_at,updated_at)
            VALUES (:s,:n,:src,:t,:sp,:cost,:ca,:ua)"""),
            {"s": slug, "n": name,
             "src": json.dumps(source_slugs or [], ensure_ascii=False),
             "t": json.dumps(template, ensure_ascii=False),
             "sp": system_prompt, "cost": cost_usd,
             "ca": exists or now, "ua": now})
    return get_genre_template(slug)


def get_genre_template(slug: str) -> dict | None:
    init()
    with _engine.begin() as c:
        r = c.execute(text("SELECT * FROM genre_template WHERE slug=:s"), {"s": slug}).mappings().first()
    if not r:
        return None
    d = dict(r)
    d["template"] = json.loads(d.pop("template_json") or "{}")
    d["source_slugs"] = json.loads(d.pop("source_slugs_json") or "[]")
    return d


def list_genre_templates() -> list[dict]:
    init()
    with _engine.begin() as c:
        rows = c.execute(text("SELECT slug,name,source_slugs_json,updated_at FROM genre_template "
                              "ORDER BY id DESC")).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["source_slugs"] = json.loads(d.pop("source_slugs_json") or "[]")
        out.append(d)
    return out


def get_config(key: str, default=None):
    init()
    with _engine.begin() as c:
        r = c.execute(text("SELECT value_json FROM app_config WHERE key=:k"), {"k": key}).scalar()
    return json.loads(r) if r else default


def save_config(key: str, value) -> None:
    init()
    with _engine.begin() as c:
        c.execute(text("INSERT OR REPLACE INTO app_config(key,value_json,updated_at) VALUES (:k,:v,:t)"),
                  {"k": key, "v": json.dumps(value, ensure_ascii=False),
                   "t": datetime.now(timezone.utc).isoformat()})


def get_genre_sample_config() -> dict:
    return get_config("genre_sample", {}) or {}


def save_genre_sample_config(cfg: dict) -> dict:
    save_config("genre_sample", cfg)
    return cfg


def delete_genre_template(slug: str) -> bool:
    init()
    with _engine.begin() as c:
        r = c.execute(text("DELETE FROM genre_template WHERE slug=:s"), {"s": slug})
    return bool(r.rowcount)


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
    # 写 compose 标记到书目录 → 墨笔书架据此识别并隐藏(compose 虚拟书是墨析的生成产物,
    # 与墨笔共享 data/books/ 会串进墨笔书架;标记后墨笔前端过滤掉,墨析侧仍照常用)。
    try:
        from app.books import library as _lib
        d = _lib.book_dir(cslug)
        if d.is_dir():
            (d / "compose.json").write_text(
                json.dumps({"is_compose": True, "use_case": use_case, "project_slug": project_slug},
                           ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
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
