"""Phase 0/1 编排器:对一个 project 的成员书**串行**跑分析。

MVP 聚焦新分析层(chapter_beat);成员书的原始抽取/风格/笔法仍走现有续写项目
的 pipeline(此处提供 ensure_* 钩子,可选触发)。串行 = 避免账号级 429。
"""
from __future__ import annotations

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from app.books import library  # noqa: E402
from app.db import book_scope  # noqa: E402  进程级绑定,防多进程写串库
from ..analysis import beat, worldview, relationship, golden, pov, style  # noqa: E402
from . import store as project_store  # noqa: E402

# 进程内 job 状态(MVP;重启即丢,够用)。
_JOBS: dict[str, dict] = {}

# Phase 1 全分析层。pov 依赖 beat,故置于 beat 之后(派生,零 LLM)。style=文笔画像。
ALL_LAYERS = ["beat", "worldview", "relationship", "golden", "pov", "style"]


def _book_slugs_of(pslug: str) -> list[str]:
    p = project_store.get_project(pslug)
    return (p or {}).get("member_book_slugs", [])


def analyze_book_beats(slug: str, *, max_chapters: int | None = None) -> dict:
    """对单本书跑 chapter_beat + 聚合卡。"""
    tag = beat.tag_beats(slug, max_chapters=max_chapters)
    summ = beat.beat_summary(slug)
    return {"slug": slug, "tag": tag, "card": summ.get("card")}


def analyze_book_layer(slug: str, layer: str, *, max_chapters: int | None = None) -> dict:
    """对单本书跑指定分析层。返回 {layer, count, card?}。"""
    if layer == "beat":
        r = beat.tag_beats(slug, max_chapters=max_chapters)
        return {"layer": layer, "count": r.get("beats"), "card": beat.beat_summary(slug).get("card")}
    if layer == "worldview":
        r = worldview.tag_reveals(slug, max_chapters=max_chapters)
        return {"layer": layer, "count": r.get("reveals"), "card": worldview.summarize(slug).get("card")}
    if layer == "relationship":
        r = relationship.tag_events(slug, max_chapters=max_chapters)
        return {"layer": layer, "count": r.get("events"), "card": relationship.summarize(slug).get("card")}
    if layer == "golden":
        r = golden.tag_steps(slug, max_chapters=max_chapters)
        return {"layer": layer, "count": r.get("steps"), "card": golden.summarize(slug).get("card")}
    if layer == "pov":
        r = pov.derive_events(slug)        # 派生自 beat,无 max_chapters
        return {"layer": layer, "count": r.get("events"), "card": r.get("card")}
    if layer == "style":
        r = style.run_style(slug)          # 文笔画像(声音/句式/语域/词汇/套路/范文)
        return {"layer": layer, "count": 1 if r.get("ok") else 0}
    raise ValueError(f"unknown layer {layer}")


def analyze_book_all(slug: str, *, layers: list[str] | None = None,
                     max_chapters: int | None = None) -> dict:
    """对单本书串行跑所有(或指定)分析层。

    全程 book_scope(slug):即便服务/前端同时把全局 active 切到别的书,本次写入
    也精确落到 slug 的库,不会串库。
    """
    layers = layers or ALL_LAYERS
    out = {}
    with book_scope(slug):
        for ly in layers:
            try:
                out[ly] = analyze_book_layer(slug, ly, max_chapters=max_chapters)
            except Exception as e:  # noqa: BLE001
                out[ly] = {"layer": ly, "error": str(e)[:160]}
    return {"slug": slug, "layers": out}


def run_project_beats(pslug: str, *, max_chapters: int | None = None) -> dict:
    """[兼容旧路由] 只跑 beat。"""
    return _run_project(pslug, layers=["beat"], max_chapters=max_chapters)


def run_project_analysis(pslug: str, *, layers: list[str] | None = None,
                         max_chapters: int | None = None) -> dict:
    """串行对 project 所有成员书跑全分析层。"""
    return _run_project(pslug, layers=layers or ALL_LAYERS, max_chapters=max_chapters)


def _run_project(pslug: str, *, layers: list[str], max_chapters: int | None) -> dict:
    slugs = _book_slugs_of(pslug)
    job = {"project": pslug, "status": "running", "total": len(slugs), "done": 0,
           "current": None, "layers": layers, "per_book": {}}
    _JOBS[pslug] = job
    try:
        for slug in slugs:
            job["current"] = slug
            try:
                r = analyze_book_all(slug, layers=layers, max_chapters=max_chapters)
                job["per_book"][slug] = {"status": "done",
                                         "counts": {ly: v.get("count") for ly, v in r["layers"].items()}}
            except Exception as e:  # noqa: BLE001 — 单书失败不连累其它
                job["per_book"][slug] = {"status": "failed", "error": str(e)[:160]}
            job["done"] += 1
        job["status"] = "done"
        job["current"] = None
    except Exception as e:  # noqa: BLE001
        job["status"] = "failed"
        job["error"] = str(e)[:200]
    return job


def job_status(pslug: str) -> dict:
    return _JOBS.get(pslug) or {"status": "idle", "project": pslug}
