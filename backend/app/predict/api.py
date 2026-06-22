from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import desc, select

from ..config import DEFAULT_CANDIDATES
from ..db import session_scope
from ..memory.models import PredictionRun
from . import arc as arc_pipeline
from ..arc import project as projection
from ..arc import bookwriter
from .pipeline import _gather_context, run_predict, stage_c_stream

router = APIRouter()


# ---------------------------------------------------------------------------
# Whole-story arc prediction
# ---------------------------------------------------------------------------


class ArcRunRequest(BaseModel):
    after_chapter: int
    n_candidates: int = 3
    target_chapters: int = 100
    user_hints: str = ""


@router.post("/arc/run")
def arc_run(req: ArcRunRequest):
    return arc_pipeline.run_arc(
        req.after_chapter,
        n_candidates=req.n_candidates,
        target_chapters=req.target_chapters,
        user_hints=req.user_hints,
    )


@router.get("/arc/runs")
def arc_runs(limit: int = 30):
    return arc_pipeline.list_runs(limit=limit)


@router.get("/arc/runs/{run_id}")
def arc_get_run(run_id: int):
    r = arc_pipeline.get_run(run_id)
    if not r:
        raise HTTPException(404)
    return r


# ---------------------------------------------------------------------------
# Whole-book story projection (整本故事弧推演)
# ---------------------------------------------------------------------------


class ProjectRequest(BaseModel):
    chosen_index: int = 0


@router.post("/arc/runs/{run_id}/project")
def arc_project(run_id: int, body: ProjectRequest, background: BackgroundTasks):
    """Expand the chosen arc's phases into a continuous whole-book outline.
    Background — poll /predict/projections/{id}."""
    jid = projection.create_job(run_id, body.chosen_index)
    background.add_task(projection.run_and_store, jid, run_id, body.chosen_index)
    return {"id": jid, "status": "projecting"}


@router.get("/projections")
def projections_list(limit: int = 20):
    return projection.list_jobs(limit=limit)


@router.get("/projections/{job_id}")
def projection_get(job_id: int):
    r = projection.get_job(job_id)
    if not r:
        raise HTTPException(404)
    return r


# ---------------------------------------------------------------------------
# B · 滚动地平线整本书写作（write-book）
# ---------------------------------------------------------------------------


class WriteBookRequest(BaseModel):
    max_chapters: int | None = None   # 分批：一次写几章（None=全部）
    max_phases: int | None = None     # 阶段 gate：写满 N 个阶段即暂停待人审（None=不限）
    skip_reviews: bool = False
    reingest: bool = True             # 每章写完同步回灌记忆（A）


@router.post("/projections/{projection_id}/write-book")
def write_book(projection_id: int, body: WriteBookRequest, background: BackgroundTasks):
    """按 projection 的逐-phase OutlineRun 顺序逐章成稿 + 同步回灌；可续写/分批/阶段 gate。"""
    jid = bookwriter.create_job(projection_id)
    background.add_task(bookwriter.run_and_store, jid, projection_id,
                        body.max_chapters, body.skip_reviews, body.reingest, body.max_phases)
    return {"id": jid, "status": "writing"}


@router.get("/book-writes")
def book_writes_list(limit: int = 20):
    return bookwriter.list_jobs(limit=limit)


@router.get("/book-writes/{job_id}")
def book_write_get(job_id: int):
    r = bookwriter.get_job(job_id)
    if not r:
        raise HTTPException(404)
    return r


class RunRequest(BaseModel):
    after_chapter: int
    candidates: int = DEFAULT_CANDIDATES


@router.post("/run")
def run(req: RunRequest):
    return run_predict(req.after_chapter, n=req.candidates)


@router.get("/runs")
def list_runs(limit: int = 30):
    with session_scope() as s:
        rows = s.execute(
            select(PredictionRun).order_by(desc(PredictionRun.id)).limit(limit)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "after_chapter": r.after_chapter,
                "chosen_index": r.chosen_index,
                "cost_usd": r.cost_usd,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "candidates": r.candidates_json,
                "scores": r.scores_json,
                "has_text": bool(r.written_text),
            }
            for r in rows
        ]


@router.get("/runs/{run_id}")
def get_run(run_id: int):
    with session_scope() as s:
        r = s.get(PredictionRun, run_id)
        if not r:
            raise HTTPException(404)
        return {
            "id": r.id,
            "after_chapter": r.after_chapter,
            "chosen_index": r.chosen_index,
            "candidates": r.candidates_json,
            "scores": r.scores_json,
            "written_text": r.written_text,
            "cost_usd": r.cost_usd,
        }


class WriteRequest(BaseModel):
    run_id: int
    chosen_index: int


@router.post("/write")
def write(req: WriteRequest):
    with session_scope() as s:
        run = s.get(PredictionRun, req.run_id)
        if not run:
            raise HTTPException(404, "no such run")
        cands = run.candidates_json or []
        if req.chosen_index < 0 or req.chosen_index >= len(cands):
            raise HTTPException(400, "chosen_index out of range")
        chosen = cands[req.chosen_index]
        after = run.after_chapter

    ctx = _gather_context(after)
    accumulated: list[str] = []

    def gen():
        for chunk in stage_c_stream(chosen, ctx, after_chapter=after):
            accumulated.append(chunk)
            yield chunk
        # Persist after stream finishes.
        with session_scope() as s:
            r = s.get(PredictionRun, req.run_id)
            r.chosen_index = req.chosen_index
            r.written_text = "".join(accumulated)

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")
