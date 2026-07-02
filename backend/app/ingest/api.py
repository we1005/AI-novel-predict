from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from ..db import session_scope
from ..memory.models import Chapter, ExtractionBatch
from .extract import run_all, run_batch
from ..books import library
from ..db import book_scope


def _scoped(slug, fn, *a, **k):
    # 修复 F5(红蓝对抗):后台抽取在请求线程捕获 active slug,用 book_scope 进程级绑定,
    # 防执行期间用户切书把抽取结果写进别的库(active_book 是共享文件,get_active 无锁)。
    from contextlib import nullcontext
    with (book_scope(slug) if slug else nullcontext()):
        return fn(*a, **k)
from .split import ingest as ingest_corpus

router = APIRouter()


class IngestRequest(BaseModel):
    # Optional: split an external file. If omitted, splits the active book's
    # already-imported corpus.txt — the normal path after /books/import.
    path: str | None = None


@router.post("/split")
def split_endpoint(req: IngestRequest | None = None):
    from ..books.library import active_paths

    if req and req.path:
        # 修复 D6(红蓝对抗):防路径穿越。旧代码对 req.path 不做限制,
        # POST {path:"../../.env"} 既能泄露任意文件首尾,又会覆写当前活动书语料并清表。
        # 只允许 data 目录内的文件。详见 docs/架构红蓝对抗-质疑与验证.md。
        p = Path(req.path).resolve()
        data_root = active_paths()["corpus_txt"].resolve().parents[2]  # .../backend/data
        try:
            p.relative_to(data_root)
        except ValueError:
            raise HTTPException(403, f"path must be inside the data directory: {data_root}")
    else:
        p = active_paths()["corpus_txt"]
    if not p.exists():
        raise HTTPException(404, f"file not found: {p}")
    try:
        return ingest_corpus(p)
    except RuntimeError as e:
        # 切分失败(未检测到章节 / 无法解码)属于"这本书的数据不合规",不是服务器故障。
        # 必须转成带 CORS 头的 4xx —— 未捕获异常会走 FastAPI 的 500,而 500 由最外层的
        # ServerErrorMiddleware 生成、绕过 CORSMiddleware,响应没有 Access-Control-Allow-Origin,
        # 浏览器只会报成"CORS 被拦"(掩盖真实原因)。见 docs/实验与操作台账.md。
        msg = str(e)
        if "no chapters detected" in msg:
            msg = (
                "未检测到章节:该书正文没有「第N章」式标题(切分器锚定『第<数字>章』,"
                "允许前导空格/全角空格)。请确认导入的是章回体小说,或到「书库」换一本;"
                f"若确为其它标记(第N回/节/幕等)请提需求扩充切分规则。(原始:{msg})"
            )
        raise HTTPException(422, msg)


@router.get("/chapters/count")
def chapter_count():
    with session_scope() as s:
        total = s.scalar(select(func.count(Chapter.number))) or 0
        first = s.scalar(select(func.min(Chapter.number))) or 0
        last = s.scalar(select(func.max(Chapter.number))) or 0
    return {"total": total, "first": first, "last": last}


@router.get("/recommend-batch")
def recommend_batch():
    """按本书体量(章数)与每章中位字数,推荐「每批章数 / 并发」默认值。

    抽取是**输出 token 瓶颈**:每批喂给 6 个 agent 的文本越多、产出越易被截/漏抽
    (改进记录 #20)。所以每批章数应与每章字数成反比——长章每批要小、短章可大。
    目标:每批输入文本量稳定在 ~22000 字的舒适窗口。
    """
    with session_scope() as s:
        rows = s.execute(select(Chapter.char_offset_start, Chapter.char_offset_end)).all()
    lens = sorted(max(0, (e or 0) - (st or 0)) for st, e in rows)
    lens = [x for x in lens if x > 0]
    total = len(lens)
    if not lens:
        return {"batch_size": 10, "workers": 3, "median_chars": 0, "total_chapters": 0,
                "rationale": "尚未切分章节;切分后会按体量给出推荐。"}
    median = lens[len(lens) // 2]

    TARGET_CHARS_PER_BATCH = 22000
    batch_size = max(1, min(12, round(TARGET_CHARS_PER_BATCH / median)))
    # 并发:账号级频率限制(AccountRateLimitExceeded)是真正的上限,高并发必爆 429,
    # 故保守封顶——长章 1、其余 2(配合 429 长退避足够稳;要更快可手动调高自担风险)。
    workers = 1 if median > 12000 else 2
    est_batches = max(1, -(-total // batch_size))  # ceil
    rationale = (
        f"全书 {total} 章、中位 {median} 字/章 → 每批 {batch_size} 章(约 "
        f"{batch_size * median} 字/批,贴近 ~{TARGET_CHARS_PER_BATCH} 字舒适窗口)、"
        f"并发 {workers} → 约 {est_batches} 批。长章每批小、短章每批大,以防输出被截漏抽。"
    )
    return {"batch_size": batch_size, "workers": workers, "median_chars": median,
            "total_chapters": total, "est_batches": est_batches, "rationale": rationale}


@router.post("/extract")
async def extract_endpoint(start: int, end: int, background: BackgroundTasks):
    if end <= start:
        raise HTTPException(400, "end must be > start")
    background.add_task(_scoped, library.get_active(), run_batch, start, end)
    return {"queued": {"start": start, "end": end}}


@router.post("/extract/all")
async def extract_all_endpoint(
    background: BackgroundTasks,
    batch_size: int = 50,
    workers: int = 2,
):
    """Kick off extraction for every batch that isn't already 'done' or
    overlapping with a running batch. Background. Poll /ingest/batches."""
    background.add_task(_scoped, library.get_active(), run_all, batch_size=batch_size, workers=workers)
    # Compute the planned work so the UI can show "N batches queued".
    with session_scope() as s:
        from sqlalchemy import func as _f
        total = s.scalar(select(_f.count(Chapter.number))) or 0
        first = s.scalar(select(_f.min(Chapter.number))) or 0
        last = s.scalar(select(_f.max(Chapter.number))) or 0
        existing = [
            (b.chapter_start, b.chapter_end, b.status)
            for b in s.execute(
                select(ExtractionBatch).where(
                    ExtractionBatch.status.in_(["done", "running", "pending"])
                )
            ).scalars()
        ]
    if total == 0:
        return {"queued": 0, "skipped": 0, "msg": "no chapters — split first"}

    planned: list[list[int]] = []
    skipped_done: list[list[int]] = []
    skipped_running: list[list[int]] = []
    for start in range(first, last + 1, batch_size):
        end = min(start + batch_size, last + 1)
        overlap = next(
            ((s_, e_, st) for s_, e_, st in existing if start < e_ and s_ < end),
            None,
        )
        if overlap is None:
            planned.append([start, end])
        elif overlap[2] == "done":
            skipped_done.append([start, end])
        else:
            skipped_running.append([start, end])

    return {
        "queued": len(planned),
        "skipped_done": len(skipped_done),
        "skipped_running": len(skipped_running),
        "batch_size": batch_size,
        "workers": workers,
        "first": first,
        "last": last,
        "ranges_queued": planned[:8],
    }


def _coverage_set() -> set[int]:
    """Set of chapter numbers covered by any 'done' batch."""
    with session_scope() as s:
        rows = s.execute(
            select(ExtractionBatch).where(ExtractionBatch.status == "done")
        ).scalars().all()
        out: set[int] = set()
        for r in rows:
            for ch in range(r.chapter_start, r.chapter_end):
                out.add(ch)
        return out


@router.get("/coverage")
def extraction_coverage() -> dict:
    """Which chapters of the active book are still missing extraction?
    Drives the page-level integrity indicator."""
    with session_scope() as s:
        from sqlalchemy import func as _f
        first = s.scalar(select(_f.min(Chapter.number))) or 0
        last = s.scalar(select(_f.max(Chapter.number))) or 0
    if last == 0:
        return {"first": 0, "last": 0, "total": 0, "covered": 0,
                "missing": [], "missing_ranges": []}

    covered = _coverage_set()
    all_chs = set(range(first, last + 1))
    missing = sorted(all_chs - covered)
    # Compress to ranges for compact display.
    ranges: list[list[int]] = []
    cur_start = None
    prev = None
    for n in missing:
        if cur_start is None:
            cur_start = n
            prev = n
        elif n == prev + 1:
            prev = n
        else:
            ranges.append([cur_start, prev])
            cur_start = n
            prev = n
    if cur_start is not None:
        ranges.append([cur_start, prev])
    return {
        "first": first,
        "last": last,
        "total": last - first + 1,
        "covered": len(all_chs & covered),
        "missing": missing[:50],   # head only — for tooltip
        "missing_ranges": ranges,
    }


@router.post("/batches/{batch_id}/retry")
def retry_batch(batch_id: int, background: BackgroundTasks) -> dict:
    """Retry a failed batch. Crucially: uses the row's original (start, end) —
    user cannot accidentally pick a different range. If those chapters are
    already covered by other 'done' batches, this row is marked 'superseded'
    without spending any tokens."""
    with session_scope() as s:
        b = s.get(ExtractionBatch, batch_id)
        if b is None:
            raise HTTPException(404, "batch not found")
        if b.status != "failed":
            raise HTTPException(
                400,
                f"batch is {b.status!r}, not failed — only failed batches "
                "can be retried",
            )
        start, end = b.chapter_start, b.chapter_end

    # Coverage check
    covered = _coverage_set()
    requested = set(range(start, end))
    gap = sorted(requested - covered)

    if not gap:
        # Fully covered — don't run, just record.
        with session_scope() as s:
            b = s.get(ExtractionBatch, batch_id)
            b.status = "superseded"
            b.error = (
                f"failed range [{start},{end}) is fully covered by other "
                "done batches — marked superseded without re-running"
            )
        return {
            "id": batch_id,
            "action": "superseded",
            "range": [start, end],
            "covered_chapters": len(requested),
            "gap_chapters": [],
        }

    # Has gaps — actually re-run. run_batch creates a fresh ExtractionBatch
    # row, so the old failed row stays as historical record.
    background.add_task(_scoped, library.get_active(), run_batch, start, end)
    return {
        "id": batch_id,
        "action": "retrying",
        "range": [start, end],
        "covered_chapters": len(requested - set(gap)),
        "gap_chapters": gap[:20],
        "gap_total": len(gap),
        "msg": f"retry queued for [{start},{end}); {len(gap)} of "
               f"{end - start} chapters not yet covered by another batch",
    }


class CleanupPayload(BaseModel):
    older_than_minutes: int = 30


@router.post("/batches/cleanup-stuck")
def cleanup_stuck_batches(body: CleanupPayload | None = None) -> dict:
    """Mark long-running batches as failed. After a backend restart or hard
    crash, the in-memory ThreadPool is gone but the DB row still says
    'running' — those rows block new work via the overlap check."""
    from datetime import datetime, timedelta

    # 修复 G4(红蓝对抗):钳最小 5 分钟,防 older_than_minutes=0 把刚启动、线程仍在跑的批次误标 failed。
    threshold = max(5, (body.older_than_minutes if body else 30))
    cutoff = datetime.utcnow() - timedelta(minutes=threshold)
    cleaned: list[dict] = []
    with session_scope() as s:
        rows = s.execute(
            select(ExtractionBatch).where(
                ExtractionBatch.status.in_(["running", "pending"]),
                ExtractionBatch.created_at < cutoff,
            )
        ).scalars().all()
        for r in rows:
            cleaned.append({
                "id": r.id, "range": [r.chapter_start, r.chapter_end],
                "started": r.created_at.isoformat() if r.created_at else None,
            })
            r.status = "failed"
            r.error = f"marked stale (>{threshold} min) by cleanup"
    return {"cleaned": len(cleaned), "items": cleaned, "older_than_minutes": threshold}


@router.get("/batches")
def batches():
    with session_scope() as s:
        rows = s.execute(select(ExtractionBatch).order_by(ExtractionBatch.id.desc())).scalars().all()
        return [
            {
                "id": r.id,
                "chapter_start": r.chapter_start,
                "chapter_end": r.chapter_end,
                "status": r.status,
                "cost_usd": r.cost_usd,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
            for r in rows
        ]
