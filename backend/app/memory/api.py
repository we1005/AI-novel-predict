from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
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
    from ..settings.store import get_vector_recall_enabled

    fts_hits = fts_recall.search(req.query, limit=req.k, before_chapter=req.before_chapter)
    vec_err = None
    vec_hits: list[dict] = []
    enabled = get_vector_recall_enabled()
    # E2:向量层默认关闭,关闭时**完全不碰**(不加载模型、不建客户端);开关打开后才查询。
    if enabled:
        try:
            vec_hits = vec_recall.query(req.query, k=req.k, before_chapter=req.before_chapter)
        except Exception as exc:  # 打开但出错(未建索引/依赖缺/模型下载失败)→ 暴露真因,不静默吞。
            vec_err = str(exc) or exc.__class__.__name__
    else:
        vec_err = "disabled"  # 前端据此显示"向量层未启用",而非误以为"没结果"。
    return {"fts": fts_hits, "vector": vec_hits, "vector_error": vec_err, "vector_enabled": enabled}


# ---------------------------------------------------------------------------
# E2:向量层(语义检索)启用 / 状态 / 手动建索引
# ---------------------------------------------------------------------------

@router.get("/vector/status")
def vector_status():
    """前端「语义检索」卡片用:开关 / 依赖是否装 / 模型是否已加载 / 已索引片段数 /
    上次建索引进度。状态查询保持廉价(不加载嵌入模型)。"""
    from ..config import EMBEDDING_MODEL
    from ..settings.store import get_vector_recall_enabled

    return {
        "enabled": get_vector_recall_enabled(),
        "deps_installed": vec_recall.deps_available(),
        "model_loaded": vec_recall.model_loaded(),
        "indexed_count": vec_recall.indexed_count(),
        "reindex": vec_recall.reindex_state(),
        "embedding_model": EMBEDDING_MODEL,
    }


@router.post("/vector/reindex")
def vector_reindex(background: BackgroundTasks):
    """手动「加载模型并建立索引」:对当前活动书全量重嵌入。后台运行(首次会加载/
    下载嵌入模型,耗时);前端轮询 /vector/status 看 reindex 进度。
    需先在设置里打开开关,否则拒绝(避免误触发重型加载)。"""
    from contextlib import nullcontext

    from ..books import library
    from ..db import book_scope
    from ..settings.store import get_vector_recall_enabled

    if not get_vector_recall_enabled():
        raise HTTPException(400, "向量层未启用 —— 请先在设置里打开「语义检索」开关")
    if not vec_recall.deps_available():
        raise HTTPException(
            400,
            "向量依赖未安装 —— 请在 backend 下运行 "
            "`.venv/bin/python -m pip install chromadb sentence-transformers`",
        )
    st = vec_recall.reindex_state()
    if st.get("status") == "running":
        raise HTTPException(409, "索引正在构建中,请稍候")

    slug = library.get_active()

    def _run():
        # 与抽取一致:进程级绑定 active book,防构建期间用户切书把向量写进别的库。
        with (book_scope(slug) if slug else nullcontext()):
            try:
                vec_recall.reindex_active_book()
            except Exception:
                pass  # 进度/错误已写入 reindex_state,前端轮询可见

    background.add_task(_run)
    return {"queued": True, "book": slug}
