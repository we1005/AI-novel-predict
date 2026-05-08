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
        p = Path(req.path)
    else:
        p = active_paths()["corpus_txt"]
    if not p.exists():
        raise HTTPException(404, f"file not found: {p}")
    return ingest_corpus(p)


@router.get("/chapters/count")
def chapter_count():
    with session_scope() as s:
        total = s.scalar(select(func.count(Chapter.number))) or 0
        first = s.scalar(select(func.min(Chapter.number))) or 0
        last = s.scalar(select(func.max(Chapter.number))) or 0
    return {"total": total, "first": first, "last": last}


@router.post("/extract")
async def extract_endpoint(start: int, end: int, background: BackgroundTasks):
    if end <= start:
        raise HTTPException(400, "end must be > start")
    background.add_task(run_batch, start, end)
    return {"queued": {"start": start, "end": end}}


@router.post("/extract/all")
async def extract_all_endpoint(
    background: BackgroundTasks,
    batch_size: int = 50,
    workers: int = 2,
):
    """Kick off extraction for every batch that isn't already 'done' or
    overlapping with a running batch. Background. Poll /ingest/batches."""
    background.add_task(run_all, batch_size=batch_size, workers=workers)
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
    background.add_task(run_batch, start, end)
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

    threshold = (body.older_than_minutes if body else 30)
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
