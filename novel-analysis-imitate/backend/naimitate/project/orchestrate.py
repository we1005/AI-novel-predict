"""Phase 0/1 编排器:对一个 project 的成员书**串行**跑分析。

MVP 聚焦新分析层(chapter_beat);成员书的原始抽取/风格/笔法仍走现有续写项目
的 pipeline(此处提供 ensure_* 钩子,可选触发)。串行 = 避免账号级 429。
"""
from __future__ import annotations

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from app.books import library  # noqa: E402
from ..analysis import beat  # noqa: E402
from . import store as project_store  # noqa: E402

# 进程内 job 状态(MVP;重启即丢,够用)。
_JOBS: dict[str, dict] = {}


def _book_slugs_of(pslug: str) -> list[str]:
    p = project_store.get_project(pslug)
    return (p or {}).get("member_book_slugs", [])


def analyze_book_beats(slug: str, *, max_chapters: int | None = None) -> dict:
    """对单本书跑 chapter_beat + 聚合卡。"""
    tag = beat.tag_beats(slug, max_chapters=max_chapters)
    summ = beat.beat_summary(slug)
    return {"slug": slug, "tag": tag, "card": summ.get("card")}


def run_project_beats(pslug: str, *, max_chapters: int | None = None) -> dict:
    """串行对 project 所有成员书跑 beat。写进程内 job 状态供轮询。"""
    slugs = _book_slugs_of(pslug)
    job = {"project": pslug, "status": "running", "total": len(slugs), "done": 0,
           "current": None, "per_book": {}}
    _JOBS[pslug] = job
    try:
        for slug in slugs:
            job["current"] = slug
            try:
                r = analyze_book_beats(slug, max_chapters=max_chapters)
                job["per_book"][slug] = {"status": "done", "beats": r["tag"].get("beats"),
                                         "card": r.get("card")}
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
