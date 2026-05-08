"""Build/refresh CharacterProfile rows for top-N person entities.

Per-character LLM call (parallel via ThreadPool). Each call sees only that
character's slice of the structured data — not the whole entity table —
so the prompts stay bounded.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from sqlalchemy import asc, desc, select

from ..config import MODEL_FAST
from ..db import session_scope
from ..llm import client as llm
from ..llm.prompts.profile import PROFILE_SYSTEM, PROFILE_TOOL
from ..memory.models import (
    CharacterProfile,
    Entity,
    EntityState,
    Foreshadowing,
    PlotPoint,
    Relationship,
)


def _gather_for_character(entity_id: int, max_chapter: int | None) -> dict[str, Any]:
    with session_scope() as s:
        ent = s.get(Entity, entity_id)
        if not ent:
            return {}

        # state diffs
        state_q = select(EntityState).where(EntityState.entity_id == entity_id)
        if max_chapter is not None:
            state_q = state_q.where(EntityState.chapter <= max_chapter)
        states = s.execute(state_q.order_by(asc(EntityState.chapter))).scalars().all()
        state_dump = [
            {
                "chapter": st.chapter,
                "state": st.state_json,
                "diff": st.diff_json,
                "note": (st.note or "")[:200],
            }
            for st in states
        ]

        # relationships (both directions)
        rels = s.execute(
            select(Relationship).where(
                (Relationship.from_entity_id == entity_id)
                | (Relationship.to_entity_id == entity_id)
            )
        ).scalars().all()
        ent_by_id = {e.id: e for e in s.execute(select(Entity)).scalars().all()}
        rel_dump = []
        for r in rels:
            other_id = r.to_entity_id if r.from_entity_id == entity_id else r.from_entity_id
            other = ent_by_id.get(other_id)
            rel_dump.append({
                "other_name": other.name if other else "?",
                "direction": "out" if r.from_entity_id == entity_id else "in",
                "label": r.label,
                "description": (r.description or "")[:200],
                "first_chapter": r.first_chapter,
                "weight": r.weight,
                "status": r.status,
            })

        # foreshadowings
        fs_q = select(Foreshadowing).where(
            Foreshadowing.related_entity_ids_json.contains([entity_id])
        )
        if max_chapter is not None:
            fs_q = fs_q.where(Foreshadowing.planted_chapter <= max_chapter)
        fs_all = s.execute(fs_q).scalars().all()
        fs_dump = [
            {
                "id": f.id,
                "type": f.type,
                "status": f.status,
                "planted": f.planted_chapter,
                "resolved": f.resolved_chapter,
                "description": (f.description or "")[:200],
                "resolved_desc": (f.resolved_description or "")[:200] if f.resolved_description else None,
            }
            for f in fs_all
        ]

        # plot points involving this character
        plot_q = select(PlotPoint).where(
            PlotPoint.involved_entity_ids_json.contains([entity_id]),
            PlotPoint.importance >= 50,
        )
        if max_chapter is not None:
            plot_q = plot_q.where(PlotPoint.chapter <= max_chapter)
        plots = s.execute(plot_q.order_by(asc(PlotPoint.chapter))).scalars().all()
        plot_dump = [
            {"chapter": p.chapter, "imp": p.importance, "summary": (p.summary or "")[:200]}
            for p in plots
        ]

        return {
            "entity": {
                "id": ent.id,
                "name": ent.name,
                "type": ent.type,
                "first_appear_chapter": ent.first_appear_chapter,
                "importance": ent.importance,
                "role": ent.role,
                "description": (ent.description or "")[:400],
            },
            "states": state_dump,
            "relationships": rel_dump,
            "foreshadowings": fs_dump,
            "plot_points": plot_dump,
            "max_chapter": max_chapter,
        }


def _build_one(entity_id: int, max_chapter: int | None) -> tuple[bool, float]:
    data = _gather_for_character(entity_id, max_chapter)
    if not data:
        return False, 0.0
    ent = data["entity"]

    blocks = [
        llm.cached_block("【角色实体记录】\n" + llm.stable_json(ent)),
        llm.cached_block("【角色状态变更（按章节）】\n" + llm.stable_json(data["states"])),
        llm.cached_block("【角色相关关系】\n" + llm.stable_json(data["relationships"])),
        llm.cached_block("【角色相关伏笔】\n" + llm.stable_json(data["foreshadowings"])),
        llm.cached_block("【角色相关高重要剧情节点】\n" + llm.stable_json(data["plot_points"])),
    ]
    user = (
        f"为角色【{ent['name']}】构建 profile。"
        + (f"请按截至第 {max_chapter} 章的信息构建。" if max_chapter else "请基于全部已抽数据构建。")
        + "\n调用 build_character_profile。"
    )

    try:
        resp = llm.call(
            agent="profile.build",
            model=MODEL_FAST,
            system=[{"type": "text", "text": PROFILE_SYSTEM}, *blocks],
            messages=[{"role": "user", "content": user}],
            tools=[PROFILE_TOOL],
            tool_choice={"type": "tool", "name": PROFILE_TOOL["name"]},
            max_tokens=4000,
            temperature=0.3,
        )
    except Exception as exc:
        return False, 0.0

    out = (resp.tool_use or {}).get("input", {}) or {}
    if not out and resp.text:
        try:
            from json_repair import repair_json
            out = json.loads(repair_json(resp.text)) or {}
        except Exception:
            out = {}

    if not isinstance(out, dict) or not out.get("bio"):
        return False, resp.cost_usd

    with session_scope() as s:
        existing = s.execute(
            select(CharacterProfile).where(CharacterProfile.entity_id == entity_id).limit(1)
        ).scalar_one_or_none()
        if existing:
            row = existing
        else:
            row = CharacterProfile(entity_id=entity_id)
            s.add(row)

        row.bio = out.get("bio") or ""
        row.desires = out.get("desires") or []
        row.fears = out.get("fears") or []
        row.moral_compass = out.get("moral_compass") or ""
        row.voice_style = out.get("voice_style") or ""
        row.typical_actions = out.get("typical_actions") or []
        row.relationships_summary = out.get("relationships_summary") or []
        row.secrets_known = out.get("secrets_known") or []
        row.secrets_hidden = out.get("secrets_hidden") or []
        row.arc_so_far = out.get("arc_so_far") or ""
        row.last_built_chapter = max_chapter
        row.cost_usd = (row.cost_usd or 0.0) + resp.cost_usd
        row.updated_at = datetime.utcnow()

    return True, resp.cost_usd


def rebuild(*, top_n: int = 20, after_chapter: int | None = None,
            entity_ids: list[int] | None = None) -> dict[str, Any]:
    """Build profiles for top-N person entities (or a specific list)."""

    with session_scope() as s:
        if entity_ids:
            people = s.execute(
                select(Entity).where(
                    Entity.type == "person",
                    Entity.id.in_(entity_ids),
                )
            ).scalars().all()
        else:
            people = s.execute(
                select(Entity)
                .where(Entity.type == "person")
                .order_by(desc(Entity.importance))
                .limit(top_n)
            ).scalars().all()
        target_ids = [p.id for p in people]

    if not target_ids:
        return {"built": 0, "failed": 0, "cost_usd": 0.0}

    built = 0
    failed = 0
    total_cost = 0.0

    # Parallel — each call has its own session.
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_build_one, eid, after_chapter): eid for eid in target_ids}
        for fut in futs:
            try:
                ok, cost = fut.result()
                total_cost += cost
                if ok:
                    built += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

    return {
        "built": built,
        "failed": failed,
        "total_targeted": len(target_ids),
        "cost_usd": round(total_cost, 5),
    }


def list_profiles() -> list[dict[str, Any]]:
    with session_scope() as s:
        rows = s.execute(select(CharacterProfile)).scalars().all()
        ent_by_id = {e.id: e for e in s.execute(select(Entity)).scalars().all()}
        out: list[dict[str, Any]] = []
        for r in rows:
            ent = ent_by_id.get(r.entity_id)
            out.append({
                "id": r.id,
                "entity_id": r.entity_id,
                "name": ent.name if ent else None,
                "role": ent.role if ent else None,
                "importance": ent.importance if ent else None,
                "bio": r.bio,
                "desires": r.desires or [],
                "fears": r.fears or [],
                "moral_compass": r.moral_compass,
                "voice_style": r.voice_style,
                "typical_actions": r.typical_actions or [],
                "relationships_summary": r.relationships_summary or [],
                "secrets_known": r.secrets_known or [],
                "secrets_hidden": r.secrets_hidden or [],
                "arc_so_far": r.arc_so_far,
                "last_built_chapter": r.last_built_chapter,
                "cost_usd": r.cost_usd,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            })
        return sorted(out, key=lambda x: -(x.get("importance") or 0))


def get_profile(entity_id: int) -> dict[str, Any] | None:
    with session_scope() as s:
        row = s.execute(
            select(CharacterProfile).where(CharacterProfile.entity_id == entity_id).limit(1)
        ).scalar_one_or_none()
        if not row:
            return None
        ent = s.get(Entity, entity_id)
        return {
            "id": row.id,
            "entity_id": row.entity_id,
            "name": ent.name if ent else None,
            "role": ent.role if ent else None,
            "importance": ent.importance if ent else None,
            "description": ent.description if ent else None,
            "first_appear_chapter": ent.first_appear_chapter if ent else None,
            "bio": row.bio,
            "desires": row.desires or [],
            "fears": row.fears or [],
            "moral_compass": row.moral_compass,
            "voice_style": row.voice_style,
            "typical_actions": row.typical_actions or [],
            "relationships_summary": row.relationships_summary or [],
            "secrets_known": row.secrets_known or [],
            "secrets_hidden": row.secrets_hidden or [],
            "arc_so_far": row.arc_so_far,
            "last_built_chapter": row.last_built_chapter,
            "cost_usd": row.cost_usd,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
