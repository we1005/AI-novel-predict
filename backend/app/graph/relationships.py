"""One-shot LLM pass that labels character roles + extracts directed
relationships, then persists them.

Reuses already-extracted data — does not re-read the corpus. Input scope is
the top-N person entities by importance plus the structured signals around
them (state diffs / plot points / foreshadows).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import asc, delete, desc, select

from ..config import MODEL_FAST
from ..db import session_scope
from ..llm import client as llm
from ..llm.prompts.relationships import RELATIONSHIPS_SYSTEM, RELATIONSHIPS_TOOL
from ..memory.models import (
    Entity,
    EntityState,
    Foreshadowing,
    PlotPoint,
    Relationship,
)


def _coerce_list(v: Any) -> list:
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            d = json.loads(v)
            if isinstance(d, list):
                return d
        except json.JSONDecodeError:
            try:
                from json_repair import repair_json
                d = json.loads(repair_json(v))
                if isinstance(d, list):
                    return d
            except Exception:
                pass
    return []


def _gather_inputs(top_n: int) -> dict[str, Any]:
    with session_scope() as s:
        people = s.execute(
            select(Entity)
            .where(Entity.type == "person")
            .order_by(desc(Entity.importance))
            .limit(top_n)
        ).scalars().all()

        people_dump = [
            {
                "id": p.id,
                "name": p.name,
                "first_chapter": p.first_appear_chapter,
                "importance": p.importance or 0,
                "description": (p.description or "")[:160],
            }
            for p in people
        ]
        keep_ids = {p.id for p in people}

        # Collect raw relationship hints from entity_states.diff_json
        rel_lines: list[dict[str, Any]] = []
        states = s.execute(
            select(EntityState).order_by(asc(EntityState.chapter))
        ).scalars().all()
        name_by_id = {p.id: p.name for p in people}
        for st in states:
            if st.entity_id not in keep_ids:
                continue
            d = st.diff_json or {}
            changes = d.get("relationships_changed") or []
            for ch in changes:
                if not ch:
                    continue
                rel_lines.append({
                    "subject_id": st.entity_id,
                    "subject": name_by_id.get(st.entity_id),
                    "chapter": st.chapter,
                    "text": str(ch)[:160],
                })

        # high-importance plot points
        plots = s.execute(
            select(PlotPoint)
            .where(PlotPoint.importance >= 60)
            .order_by(asc(PlotPoint.chapter))
        ).scalars().all()
        plot_dump = [
            {
                "chapter": p.chapter,
                "summary": (p.summary or "")[:200],
                "involved": [
                    eid for eid in (p.involved_entity_ids_json or []) if eid in keep_ids
                ],
            }
            for p in plots
            if any(eid in keep_ids for eid in (p.involved_entity_ids_json or []))
        ]

        # active foreshadows tied to people
        fs = s.execute(select(Foreshadowing)).scalars().all()
        fs_dump = [
            {
                "id": f.id,
                "type": f.type,
                "status": f.status,
                "planted_chapter": f.planted_chapter,
                "description": (f.description or "")[:200],
                "involves": [
                    eid for eid in (f.related_entity_ids_json or []) if eid in keep_ids
                ],
            }
            for f in fs
            if any(eid in keep_ids for eid in (f.related_entity_ids_json or []))
        ]

    return {
        "people": people_dump,
        "rel_lines": rel_lines,
        "plot_points": plot_dump,
        "foreshadowings": fs_dump,
    }


def extract(*, top_n: int = 50) -> dict[str, Any]:
    state = _gather_inputs(top_n)

    blocks = [
        llm.cached_block("【人物表（按重要度 top-N）】\n" + llm.stable_json(state["people"])),
        llm.cached_block("【人物状态变更中的关系线索】\n" + llm.stable_json(state["rel_lines"])),
        llm.cached_block("【高重要度剧情节点（涉及上述人物）】\n" + llm.stable_json(state["plot_points"])),
        llm.cached_block("【关联人物的伏笔】\n" + llm.stable_json(state["foreshadowings"])),
    ]
    user = (
        f"全书 top {len(state['people'])} 位人物的结构化数据已注入 system。\n"
        f"已捕获 {len(state['rel_lines'])} 条关系变更原始记录、"
        f"{len(state['plot_points'])} 个高重要剧情节点、"
        f"{len(state['foreshadowings'])} 条关联伏笔。\n\n"
        "请：\n"
        "1) 为每个 person 给出 role 判定（protagonist / antagonist / ally / supporting / minor）\n"
        "2) 抽取重要的有向关系，要求 label 精炼有张力，weight 反映叙事权重\n"
        "调用 label_roles_and_relationships。"
    )

    resp = llm.call(
        agent="relationships.extract",
        model=MODEL_FAST,
        system=[{"type": "text", "text": RELATIONSHIPS_SYSTEM}, *blocks],
        messages=[{"role": "user", "content": user}],
        tools=[RELATIONSHIPS_TOOL],
        tool_choice={"type": "tool", "name": RELATIONSHIPS_TOOL["name"]},
        max_tokens=12000,
        temperature=0.2,
    )
    out = (resp.tool_use or {}).get("input", {}) or {}
    if not out and resp.text:
        # fallback parser
        try:
            from json_repair import repair_json
            out = json.loads(repair_json(resp.text)) or {}
        except Exception:
            out = {}

    roles = _coerce_list(out.get("roles", []))
    rels = _coerce_list(out.get("relationships", []))

    # Persist
    keep_ids: set[int] = {p["id"] for p in state["people"]}
    role_count = 0
    rel_count = 0
    with session_scope() as s:
        # apply roles
        for r in roles:
            if not isinstance(r, dict):
                continue
            eid = r.get("entity_id")
            role = r.get("role")
            if not isinstance(eid, int) or eid not in keep_ids or role not in {
                "protagonist", "antagonist", "ally", "supporting", "minor",
            }:
                continue
            ent = s.get(Entity, eid)
            if ent:
                ent.role = role
                role_count += 1

        # wipe existing auto-extracted relationships and re-insert
        s.execute(delete(Relationship))
        for rel in rels:
            if not isinstance(rel, dict):
                continue
            f_id = rel.get("from_entity_id")
            t_id = rel.get("to_entity_id")
            label = (rel.get("label") or "").strip()
            if not (isinstance(f_id, int) and isinstance(t_id, int) and label):
                continue
            if f_id == t_id:
                continue
            if f_id not in keep_ids or t_id not in keep_ids:
                continue
            try:
                row = Relationship(
                    from_entity_id=f_id,
                    to_entity_id=t_id,
                    label=label[:60],
                    description=(rel.get("description") or "")[:300],
                    first_chapter=rel.get("first_chapter"),
                    status=rel.get("status") if rel.get("status") in {"active", "ended"} else "active",
                    weight=max(1, min(10, int(rel.get("weight") or 1))),
                )
                s.add(row)
                s.flush()
                rel_count += 1
            except Exception:
                continue

    return {
        "roles_assigned": role_count,
        "relationships": rel_count,
        "cost_usd": resp.cost_usd,
        "elapsed_ms": resp.elapsed_ms,
    }


def list_relationships() -> list[dict[str, Any]]:
    with session_scope() as s:
        rows = s.execute(select(Relationship)).scalars().all()
        ent_by_id = {e.id: e for e in s.execute(select(Entity)).scalars().all()}
        out: list[dict[str, Any]] = []
        for r in rows:
            f = ent_by_id.get(r.from_entity_id)
            t = ent_by_id.get(r.to_entity_id)
            out.append({
                "id": r.id,
                "from_id": r.from_entity_id,
                "from_name": f.name if f else None,
                "to_id": r.to_entity_id,
                "to_name": t.name if t else None,
                "label": r.label,
                "description": r.description,
                "first_chapter": r.first_chapter,
                "status": r.status,
                "weight": r.weight,
            })
        return out
