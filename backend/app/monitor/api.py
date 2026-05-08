from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import desc, func, select

from ..db import session_scope
from ..memory.models import LLMCall

router = APIRouter()


@router.get("/summary")
def summary(hours: int = 168):
    """Aggregate stats over the last N hours."""

    since = datetime.utcnow() - timedelta(hours=hours)
    with session_scope() as s:
        total = s.execute(
            select(
                func.count(LLMCall.id),
                func.coalesce(func.sum(LLMCall.cost_usd), 0.0),
                func.coalesce(func.sum(LLMCall.input_tokens), 0),
                func.coalesce(func.sum(LLMCall.output_tokens), 0),
                func.coalesce(func.sum(LLMCall.cache_creation_tokens), 0),
                func.coalesce(func.sum(LLMCall.cache_read_tokens), 0),
            ).where(LLMCall.created_at >= since)
        ).one()
        per_agent = s.execute(
            select(
                LLMCall.agent,
                func.count(LLMCall.id),
                func.coalesce(func.sum(LLMCall.cost_usd), 0.0),
                func.coalesce(func.sum(LLMCall.cache_read_tokens), 0),
                func.coalesce(func.sum(LLMCall.input_tokens), 0),
            )
            .where(LLMCall.created_at >= since)
            .group_by(LLMCall.agent)
            .order_by(desc(func.sum(LLMCall.cost_usd)))
        ).all()

    cnt, cost, in_t, out_t, cw, cr = total
    cache_hit_ratio = (cr / (cr + in_t)) if (cr + in_t) else 0.0
    return {
        "since": since.isoformat(),
        "calls": cnt,
        "cost_usd": round(cost, 4),
        "input_tokens": in_t,
        "output_tokens": out_t,
        "cache_creation_tokens": cw,
        "cache_read_tokens": cr,
        "cache_hit_ratio": round(cache_hit_ratio, 3),
        "per_agent": [
            {
                "agent": a or "(unknown)",
                "calls": c,
                "cost_usd": round(co, 4),
                "cache_read_tokens": cr_,
                "input_tokens": it,
            }
            for a, c, co, cr_, it in per_agent
        ],
    }


@router.get("/recent")
def recent(limit: int = 50):
    with session_scope() as s:
        rows = s.execute(
            select(LLMCall).order_by(desc(LLMCall.id)).limit(limit)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "agent": r.agent,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cache_creation_tokens": r.cache_creation_tokens,
                "cache_read_tokens": r.cache_read_tokens,
                "elapsed_ms": r.elapsed_ms,
                "cost_usd": r.cost_usd,
            }
            for r in rows
        ]
