from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import library

router = APIRouter()


@router.get("")
def books_list() -> dict[str, Any]:
    return {
        "active": library.get_active(),
        "books": library.list_books(),
        "library_dir": str(library.LIBRARY_DIR),
        "library_files": library.list_library_files(),
    }


@router.post("/scan")
def books_scan() -> dict[str, Any]:
    """Re-scan the library folder. Doesn't modify anything — just lists."""
    return {
        "library_dir": str(library.LIBRARY_DIR),
        "files": library.list_library_files(),
    }


class ImportPayload(BaseModel):
    filename: str
    title: str | None = None
    set_active: bool = True


@router.post("/import")
def books_import(body: ImportPayload) -> dict[str, Any]:
    try:
        info = library.import_from_library(body.filename, title=body.title)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if body.set_active:
        library.set_active(info["slug"])
        info["active_after_import"] = True
    return info


class ForkPayload(BaseModel):
    parent_slug: str          # 从哪本书分叉(通常是原著)
    outline_run_id: int | None = None  # 该分支基于哪条大纲(记进元数据,便于前端/续写选用)
    branch_name: str          # 分支名(如"大纲A""稳健向""爽文向")
    set_active: bool = True


@router.post("/fork")
def books_fork(body: ForkPayload) -> dict[str, Any]:
    """把某本书克隆成一本派生「分支书」(独立 novel.db):续写与回灌只写入分支库,与原著/其它分支隔离。
    见 docs/多大纲分支-记忆隔离与回滚-架构方案.md。"""
    from sqlalchemy import func, select

    from ..db import book_scope, session_scope
    from ..draft.pipeline import reset_continuation
    from ..memory.models import Chapter

    # 基线章数 = 原著**真实**正文章数(续写从 base+1 起)。必须排除"续写登记的 0-offset 章"
    # (写作回灌给续写章登记的 FK 锚点行),否则会把 base 算大、续写起点后移。
    try:
        with book_scope(body.parent_slug):
            with session_scope() as s:
                base = int(s.scalar(
                    select(func.count()).select_from(Chapter)
                    .where(Chapter.char_offset_end > Chapter.char_offset_start)
                ) or 0)
    except Exception as e:
        raise HTTPException(400, f"读取原著章数失败:{e}")

    branch_slug = library._slug(f"{body.parent_slug}__{body.branch_name}")
    try:
        info = library.fork_book(
            body.parent_slug, branch_slug,
            branch_name=body.branch_name,
            outline_run_id=body.outline_run_id,
            base_chapter=base,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    # 克隆后把分支库里可能带来的续写产物(ch>base)清掉,确保从干净基线起步。
    cleaned = {}
    if base > 0:
        with book_scope(branch_slug):
            cleaned = reset_continuation(base + 1).get("affected", {})

    if body.set_active:
        library.set_active(branch_slug)
    return {**info, "base_chapter": base, "cleaned_on_fork": cleaned, "active": library.get_active()}


class ActivePayload(BaseModel):
    slug: str


@router.put("/active")
def books_set_active(body: ActivePayload) -> dict[str, Any]:
    try:
        library.set_active(body.slug)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"active": library.get_active()}


@router.delete("/{slug}")
def books_delete(slug: str) -> dict[str, Any]:
    try:
        library.delete_book(slug)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}
