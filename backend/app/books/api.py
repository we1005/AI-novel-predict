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
