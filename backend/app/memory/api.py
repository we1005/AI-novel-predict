from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select

from ..db import session_scope
from . import fts as fts_recall
from . import vector as vec_recall
from .models import Entity, EntityState, Foreshadowing, PlotPoint, WorldRule

router = APIRouter()


@router.get("/entities")
def list_entities(type: str | None = None, search: str | None = None, limit: int = 200):
    with session_scope() as s:
        q = select(Entity)
        if type:
            q = q.where(Entity.type == type)
        if search:
            like = f"%{search}%"
            q = q.where(Entity.name.like(like))
        q = q.order_by(desc(Entity.importance)).limit(limit)
        rows = s.execute(q).scalars().all()
        return [
            {
                "id": r.id,
                "type": r.type,
                "name": r.name,
                "aliases": r.aliases_json or [],
                "first_appear_chapter": r.first_appear_chapter,
                "description": r.description,
                "importance": r.importance,
            }
            for r in rows
        ]


@router.get("/foreshadowings")
def list_foreshadowings(status: str = "open", limit: int = 500):
    with session_scope() as s:
        q = select(Foreshadowing).order_by(Foreshadowing.planted_chapter)
        if status != "all":
            q = q.where(Foreshadowing.status == status)
        rows = s.execute(q.limit(limit)).scalars().all()
        return [
            {
                "id": r.id,
                "planted_chapter": r.planted_chapter,
                "type": r.type,
                "status": r.status,
                "description": r.description,
                "planted_excerpt": r.planted_excerpt,
                "resolved_chapter": r.resolved_chapter,
                "resolved_description": r.resolved_description,
                "related_entity_ids": r.related_entity_ids_json or [],
            }
            for r in rows
        ]


@router.get("/state/{entity_id}")
def get_state(entity_id: int, at_chapter: int | None = None):
    with session_scope() as s:
        e = s.get(Entity, entity_id)
        if not e:
            raise HTTPException(404, "no such entity")
        q = select(EntityState).where(EntityState.entity_id == entity_id)
        if at_chapter is not None:
            q = q.where(EntityState.chapter <= at_chapter)
        q = q.order_by(EntityState.chapter.desc()).limit(1)
        row = s.execute(q).scalar_one_or_none()
        return {
            "entity": {"id": e.id, "name": e.name, "type": e.type},
            "at_chapter": row.chapter if row else None,
            "state": row.state_json if row else {},
            "diff": row.diff_json if row else {},
        }


@router.get("/plot")
def list_plot(min_importance: int = 50, limit: int = 500):
    with session_scope() as s:
        q = (
            select(PlotPoint)
            .where(PlotPoint.importance >= min_importance)
            .order_by(PlotPoint.chapter)
            .limit(limit)
        )
        rows = s.execute(q).scalars().all()
        return [
            {
                "id": r.id,
                "chapter": r.chapter,
                "summary": r.summary,
                "importance": r.importance,
                "involved_entity_ids": r.involved_entity_ids_json or [],
            }
            for r in rows
        ]


@router.get("/rules")
def list_rules():
    with session_scope() as s:
        rows = s.execute(select(WorldRule).order_by(WorldRule.first_chapter)).scalars().all()
        return [
            {"term": r.term, "definition": r.definition, "first_chapter": r.first_chapter}
            for r in rows
        ]


class RecallRequest(BaseModel):
    query: str
    before_chapter: int | None = None
    k: int = 6


@router.post("/recall")
def recall(req: RecallRequest):
    fts_hits = fts_recall.search(req.query, limit=req.k, before_chapter=req.before_chapter)
    vec_err = None
    try:
        vec_hits = vec_recall.query(req.query, k=req.k, before_chapter=req.before_chapter)
    except Exception as exc:  # 修复 E2(红蓝对抗):不再把错误写死 None 掩盖"向量层未启用/异常"
        vec_hits = []
        vec_err = str(exc) or exc.__class__.__name__
    # 注:向量层 index_chapters 当前零调用点(死代码),vector 多为空且 vec_err 暴露真因;
    #     启用或清理见 docs/架构红蓝对抗-质疑与验证.md(E2)。
    return {"fts": fts_hits, "vector": vec_hits, "vector_error": vec_err}
