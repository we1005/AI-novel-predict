from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import pipeline

router = APIRouter()


class RefineRequest(BaseModel):
    source_kind: str  # "arc" | "predict"
    source_run_id: int
    chosen_index: int
    phase_index: int | None = None
    user_hints: str = ""


@router.post("/refine")
def refine(req: RefineRequest):
    try:
        return pipeline.refine(
            source_kind=req.source_kind,
            source_run_id=req.source_run_id,
            chosen_index=req.chosen_index,
            phase_index=req.phase_index,
            user_hints=req.user_hints,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/runs")
def list_runs(limit: int = 50):
    return pipeline.list_runs(limit=limit)


@router.get("/runs/{run_id}")
def get_run(run_id: int):
    r = pipeline.get_run(run_id)
    if not r:
        raise HTTPException(404)
    return r


class ChapterPatch(BaseModel):
    title: str | None = None
    intent: str | None = None
    must_include: list[str] | None = None
    must_avoid: list[str] | None = None
    key_events: list[str] | None = None
    foreshadow_ids_addressed: list[int] | None = None
    foreshadow_ids_planted: list[int] | None = None
    involved_entities: list[str] | None = None
    pacing: str | None = None
    word_target: int | None = None
    ending_hook: str | None = None


@router.patch("/runs/{run_id}/chapters/{chapter_index}")
def patch_chapter(run_id: int, chapter_index: int, body: ChapterPatch):
    patch: dict[str, Any] = {k: v for k, v in body.model_dump().items() if v is not None}
    if not pipeline.update_chapter(run_id, chapter_index, patch):
        raise HTTPException(404, "outline run or chapter not found")
    return {"ok": True}
