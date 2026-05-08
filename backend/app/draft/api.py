from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import pipeline

router = APIRouter()


class WriteRequest(BaseModel):
    outline_run_id: int
    chapter_index: int
    skip_reviews: bool = False
    max_attempts: int = 3


@router.post("/write")
def write(req: WriteRequest):
    try:
        return pipeline.write_chapter(
            outline_run_id=req.outline_run_id,
            chapter_index=req.chapter_index,
            skip_reviews=req.skip_reviews,
            max_attempts=req.max_attempts,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/drafts")
def list_drafts(limit: int = 50):
    return pipeline.list_drafts(limit=limit)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: int):
    r = pipeline.get_draft(draft_id)
    if not r:
        raise HTTPException(404)
    return r


class FinalTextPatch(BaseModel):
    text: str


@router.patch("/drafts/{draft_id}")
def patch_final_text(draft_id: int, body: FinalTextPatch):
    if not pipeline.update_final_text(draft_id, body.text):
        raise HTTPException(404)
    return {"ok": True}
