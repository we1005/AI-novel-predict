from __future__ import annotations

from contextlib import nullcontext

from fastapi import APIRouter

from ..db import book_scope
from . import projections, relationships as rel_pipeline
from . import dedup as dedup_pipeline

router = APIRouter()


def _scope(book: str | None):
    """图谱"视角"切换:传 book=分支slug 即把本次查询路由到该分支库(不改全局 active)。"""
    return book_scope(book) if book else nullcontext()


@router.post("/dedup")
def dedup_entities():
    return dedup_pipeline.run()


@router.post("/relationships/extract")
def extract_relationships(top_n: int = 50):
    return rel_pipeline.extract(top_n=top_n)


@router.get("/relationships")
def get_relationships(book: str | None = None):
    with _scope(book):
        return rel_pipeline.list_relationships()


@router.post("/recompute-importance")
def recompute_importance():
    n = projections.backfill_importance()
    return {"updated": n}


@router.get("/characters")
def characters(up_to_chapter: int | None = None, top_n: int = 80, book: str | None = None):
    with _scope(book):
        return projections.character_graph(up_to_chapter=up_to_chapter, top_n=top_n)


@router.get("/foreshadowings")
def foreshadowings(up_to_chapter: int | None = None, book: str | None = None):
    with _scope(book):
        return projections.foreshadow_graph(up_to_chapter=up_to_chapter)


@router.get("/timeline")
def timeline(min_importance: int = 50, book: str | None = None):
    with _scope(book):
        return projections.timeline(min_importance=min_importance)


@router.get("/hero")
def hero(entity_id: int | None = None, book: str | None = None):
    with _scope(book):
        return projections.hero_evolution(entity_id=entity_id)


@router.get("/hero-items")
def hero_items(entity_id: int | None = None, book: str | None = None):
    with _scope(book):
        return projections.hero_items(entity_id=entity_id)
