from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import pipeline
from . import suggest as _suggest

router = APIRouter()


class WriteRequest(BaseModel):
    outline_run_id: int
    chapter_index: int
    skip_reviews: bool = False
    # 修复 E5(红蓝对抗):钳制上限防"惊喜账单"(每章 ≥(1写+3审+1编)×attempts 次调用)
    max_attempts: int = Field(3, ge=1, le=10)


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
def list_drafts(limit: int = 800):
    return pipeline.list_drafts(limit=limit)


class SuggestReq(BaseModel):
    draft_id: int


@router.post("/suggest-edits")
def suggest_edits(req: SuggestReq):
    """扫描中文定稿出"就地替换"建议(不改原文) → 落库 → 返回(含实时锚点状态)。"""
    try:
        return _suggest.suggest_edits(req.draft_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e)[:240])


@router.get("/suggestions")
def get_suggestions(draft_id: int):
    """读已存的最近一批建议 + 实时重算锚点状态(对照当前定稿)。刷新后仍在。"""
    return _suggest.list_suggestions(draft_id)


class ApplyEditsReq(BaseModel):
    draft_id: int
    accepted_ids: list[int]   # 用户勾选采纳的建议 id


@router.post("/apply-edits")
def apply_edits(req: ApplyEditsReq):
    """把采纳的建议(按 id)替换进中文定稿；应用时再校验锚点，失效的计入 failed。落库 + commit。"""
    try:
        return _suggest.apply_edits(req.draft_id, req.accepted_ids)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e)[:240])


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
