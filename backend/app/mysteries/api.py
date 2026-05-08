from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import rebuild as pipeline

router = APIRouter()


class RebuildRequest(BaseModel):
    skip_existing: bool = False


@router.post("/rebuild")
def rebuild_mysteries(body: RebuildRequest | None = None):
    skip_existing = bool(body and body.skip_existing)
    return pipeline.rebuild(skip_existing=skip_existing)


@router.get("")
def list_mysteries():
    return pipeline.list_all()


@router.delete("/{mystery_id}")
def delete_mystery(mystery_id: int):
    if not pipeline.delete_one(mystery_id):
        raise HTTPException(404)
    return {"ok": True}


class NotePatch(BaseModel):
    note: str


@router.patch("/{mystery_id}")
def patch_note(mystery_id: int, body: NotePatch):
    if not pipeline.update_note(mystery_id, body.note):
        raise HTTPException(404)
    return {"ok": True}
