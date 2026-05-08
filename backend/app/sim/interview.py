"""Interview an in-novel character.

Streams a first-person answer constrained by the character's profile and
their known state up to ``after_chapter``. Persists the question/answer
pair into ``interview_logs`` for later replay.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Iterator

from sqlalchemy import asc, desc, select

from ..config import MODEL_FAST
from ..db import session_scope
from ..llm import client as llm
from ..llm.prompts.interview import INTERVIEW_SYSTEM, build_interview_user
from ..memory.models import (
    EntityState,
    InterviewLog,
)
from .profile_builder import get_profile


def _latest_state(entity_id: int, max_chapter: int) -> dict[str, Any]:
    with session_scope() as s:
        row = s.execute(
            select(EntityState)
            .where(EntityState.entity_id == entity_id, EntityState.chapter <= max_chapter)
            .order_by(desc(EntityState.chapter))
            .limit(1)
        ).scalar_one_or_none()
        if not row:
            return {}
        return {
            "as_of_chapter": row.chapter,
            "state": row.state_json,
            "last_change_note": row.note,
        }


def stream_answer(*, entity_id: int, after_chapter: int, question: str) -> Iterator[str]:
    """Yield text chunks. After the stream finishes, persist the full Q/A row."""

    profile = get_profile(entity_id)
    if not profile:
        yield f"（暂无角色档案。请先运行 POST /sim/profiles/rebuild）"
        return
    relevant_state = _latest_state(entity_id, after_chapter)

    user = build_interview_user(profile, after_chapter, question, relevant_state)
    chunks: list[str] = []

    for chunk in llm.stream_text(
        agent="interview",
        model=MODEL_FAST,
        system=INTERVIEW_SYSTEM,
        messages=[{"role": "user", "content": user}],
        max_tokens=1500,
        temperature=0.7,
    ):
        chunks.append(chunk)
        yield chunk

    answer = "".join(chunks)
    # The audit row recording cost is handled by stream_text. The Q/A archive
    # is separate — write it without a cost number (cost is in llm_calls).
    with session_scope() as s:
        s.add(
            InterviewLog(
                entity_id=entity_id,
                after_chapter=after_chapter,
                question=question,
                answer=answer,
                cost_usd=0.0,
                created_at=datetime.utcnow(),
            )
        )


def list_history(entity_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with session_scope() as s:
        q = select(InterviewLog).order_by(desc(InterviewLog.id)).limit(limit)
        if entity_id is not None:
            q = q.where(InterviewLog.entity_id == entity_id)
        rows = s.execute(q).scalars().all()
        return [
            {
                "id": r.id,
                "entity_id": r.entity_id,
                "after_chapter": r.after_chapter,
                "question": r.question,
                "answer": r.answer,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
