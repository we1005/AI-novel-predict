from __future__ import annotations

from fastapi import APIRouter

from . import projections, relationships as rel_pipeline

router = APIRouter()


@router.post("/relationships/extract")
def extract_relationships(top_n: int = 50):
    return rel_pipeline.extract(top_n=top_n)


@router.get("/relationships")
def get_relationships():
    return rel_pipeline.list_relationships()


@router.post("/recompute-importance")
def recompute_importance():
    n = projections.backfill_importance()
    return {"updated": n}


@router.get("/characters")
def characters(up_to_chapter: int | None = None, top_n: int = 80):
    return projections.character_graph(up_to_chapter=up_to_chapter, top_n=top_n)


@router.get("/foreshadowings")
def foreshadowings(up_to_chapter: int | None = None):
    return projections.foreshadow_graph(up_to_chapter=up_to_chapter)


@router.get("/timeline")
def timeline(min_importance: int = 50):
    return projections.timeline(min_importance=min_importance)


@router.get("/hero")
def hero(entity_id: int | None = None):
    return projections.hero_evolution(entity_id=entity_id)


@router.get("/hero-items")
def hero_items(entity_id: int | None = None):
    return projections.hero_items(entity_id=entity_id)
