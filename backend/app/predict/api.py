from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import desc, select

from ..config import DEFAULT_CANDIDATES
from ..db import session_scope
from ..memory.models import PredictionRun
from . import arc as arc_pipeline
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
