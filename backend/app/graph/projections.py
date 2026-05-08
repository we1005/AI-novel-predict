"""Project L1 (SQLite) into JSON shapes the frontend can render directly."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import asc, desc, func, select

from ..db import session_scope
from ..memory.models import (
    Chapter,
    Entity,
    EntityState,
    Foreshadowing,
    PlotPoint,
    Relationship,
)


# ---------------------------------------------------------------------------
# Importance backfill
# ---------------------------------------------------------------------------

def backfill_importance() -> int:
    """Recompute ``Entity.importance`` from observed activity.

    The extractor's per-batch ``importance += 1`` accounting was unreliable
    once we ran batches in parallel: every batch's EntityAgent independently
    proposed the protagonist as a "new" entity, the ``UPSERT`` path ran a
    SELECT and either bumped or no-op'd, and parallel writers occasionally
    raced through the SAVEPOINT branch where no bump happened. Net effect:
    the protagonist (林云) ended up at importance=1 — same as a one-line
    walk-on character — and a name-corrupted late-book entity took the top
    slot in every "by importance" view.

    Recompute from facts that already exist in the DB:
      * +5 for being involved in any ``plot_point`` (per occurrence)
      * +3 for each ``entity_state`` snapshot (a state diff means the entity
        actually did something)
      * +2 for each ``foreshadowing.related_entity_ids`` mention
      * +1 baseline so first_appear-only walk-ons still rank above zero
    """

    with session_scope() as s:
        plot_rows = s.execute(select(PlotPoint.involved_entity_ids_json)).scalars().all()
        plot_count: dict[int, int] = defaultdict(int)
        for ids in plot_rows:
            for eid in ids or []:
                plot_count[int(eid)] += 1

        state_rows = s.execute(
            select(EntityState.entity_id, func.count(EntityState.id)).group_by(EntityState.entity_id)
        ).all()
        state_count = {eid: n for eid, n in state_rows}

        fs_rows = s.execute(select(Foreshadowing.related_entity_ids_json)).scalars().all()
        fs_count: dict[int, int] = defaultdict(int)
        for ids in fs_rows:
            for eid in ids or []:
                fs_count[int(eid)] += 1

        all_entities = s.execute(select(Entity)).scalars().all()
        for e in all_entities:
            e.importance = (
                1
                + 5 * plot_count.get(e.id, 0)
                + 3 * state_count.get(e.id, 0)
                + 2 * fs_count.get(e.id, 0)
            )
        return len(all_entities)


# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------

def _pick_hero(session) -> Entity | None:
    """Identify the protagonist.

    First pass: any person whose ``first_appear_chapter == 1`` — virtually
    every web-serial protagonist debuts in chapter 1. If multiple match, take
    the highest-importance one.
    Fallback: highest-importance person overall (post-backfill, this is
    reliable).
    """

    chap1 = session.execute(
        select(Entity)
        .where(Entity.type == "person", Entity.first_appear_chapter == 1)
        .order_by(desc(Entity.importance))
        .limit(1)
    ).scalar_one_or_none()
    if chap1:
        return chap1
    return session.execute(
        select(Entity)
        .where(Entity.type == "person")
        .order_by(desc(Entity.importance))
        .limit(1)
    ).scalar_one_or_none()


def hero_items(entity_id: int | None = None) -> dict[str, Any]:
    """The protagonist's treasure / weapon / technique evolution.

    Source of truth is the protagonist's chronological ``entity_states`` —
    each row's ``state_json`` carries the inventory snapshot at that chapter.
    We diff consecutive snapshots to build per-name event timelines
    (gained / lost). Each item is then cross-referenced against the entity
    table (for description) and the foreshadow table (for hidden hooks tied to
    that item).

    Items often quietly carry foreshadows ("the rusted dagger his father left
    him") that pay off chapters later — surfacing this view is a fast way to
    notice setups that haven't been collected yet.
    """

    from collections import defaultdict

    with session_scope() as s:
        hero = s.get(Entity, entity_id) if entity_id else _pick_hero(s)
        if not hero:
            return {"hero": None, "items": []}
        states = s.execute(
            select(EntityState)
            .where(EntityState.entity_id == hero.id)
            .order_by(EntityState.chapter)
        ).scalars().all()

        # Diff consecutive snapshots
        events_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        kind_by_name: dict[str, str] = {}  # 'item' or 'skill' (which list it appeared in)
        prev_items: set[str] = set()
        prev_skills: set[str] = set()

        for st in states:
            sj = st.state_json or {}
            cur_items = set((sj.get("items") or []))
            cur_skills = set((sj.get("skills") or []))
            note = (st.note or "")[:200]

            for n in cur_items - prev_items:
                kind_by_name[n] = "item"
                events_by_name[n].append({"chapter": st.chapter, "kind": "gained", "note": note})
            for n in prev_items - cur_items:
                events_by_name[n].append({"chapter": st.chapter, "kind": "lost", "note": note})

            for n in cur_skills - prev_skills:
                kind_by_name[n] = "skill"
                events_by_name[n].append({"chapter": st.chapter, "kind": "gained", "note": note})
            for n in prev_skills - cur_skills:
                events_by_name[n].append({"chapter": st.chapter, "kind": "lost", "note": note})

            prev_items, prev_skills = cur_items, cur_skills

        # Lookup tables
        all_entities_by_name: dict[str, Entity] = {
            e.name: e for e in s.execute(select(Entity)).scalars().all()
        }
        all_fs = s.execute(select(Foreshadowing)).scalars().all()
        chapter_titles = dict(s.execute(select(Chapter.number, Chapter.title)).all())

    items_out: list[dict[str, Any]] = []
    for name, events in events_by_name.items():
        entity = all_entities_by_name.get(name)
        kind = kind_by_name.get(name, "item")
        if entity and entity.type in ("item", "skill", "concept"):
            kind = entity.type

        # Related foreshadows: either explicitly linked via related_entity_ids,
        # or item name appears in description (substring match — cheap heuristic).
        related_fs: list[Foreshadowing] = []
        seen_fs_ids: set[int] = set()
        for f in all_fs:
            hit = False
            if entity and entity.id in (f.related_entity_ids_json or []):
                hit = True
            elif name and len(name) >= 2 and name in (f.description or ""):
                hit = True
            if hit and f.id not in seen_fs_ids:
                related_fs.append(f)
                seen_fs_ids.add(f.id)

        first_seen = min(e["chapter"] for e in events)
        last_seen = max(e["chapter"] for e in events)
        last_kind = events[-1]["kind"]
        still_owned = last_kind != "lost"

        for ev in events:
            ev["chapter_title"] = chapter_titles.get(ev["chapter"], "")

        items_out.append({
            "name": name,
            "kind": kind,
            "first_seen_chapter": first_seen,
            "last_seen_chapter": last_seen,
            "still_owned": still_owned,
            "entity_id": entity.id if entity else None,
            "entity_importance": entity.importance if entity else None,
            "description": (entity.description or "")[:400] if entity else "",
            "events": events,
            "related_foreshadows": [
                {
                    "id": f.id,
                    "type": f.type,
                    "status": f.status,
                    "planted_chapter": f.planted_chapter,
                    "resolved_chapter": f.resolved_chapter,
                    "description": (f.description or "")[:240],
                    "resolved_description": (f.resolved_description or "")[:240] if f.resolved_description else None,
                }
                for f in related_fs
            ],
        })

    # Sort: foreshadow-rich first, then by importance.
    items_out.sort(
        key=lambda x: (
            -len(x["related_foreshadows"]),
            -(x["entity_importance"] or 0),
            x["first_seen_chapter"],
        )
    )

    return {
        "hero": {
            "id": hero.id,
            "name": hero.name,
            "description": hero.description,
            "importance": hero.importance,
        },
        "items": items_out,
    }


def hero_evolution(entity_id: int | None = None) -> dict[str, Any]:
    with session_scope() as s:
        hero = s.get(Entity, entity_id) if entity_id else _pick_hero(s)
        if not hero:
            return {"hero": None, "series": []}
        rows = s.execute(
            select(EntityState)
            .where(EntityState.entity_id == hero.id)
            .order_by(EntityState.chapter)
        ).scalars().all()
        chapter_titles = dict(s.execute(select(Chapter.number, Chapter.title)).all())

    series: list[dict[str, Any]] = []
    realm_idx_by_str: dict[str, int] = {}
    for r in rows:
        st = r.state_json or {}
        realm = st.get("realm")
        if realm and realm not in realm_idx_by_str:
            realm_idx_by_str[realm] = len(realm_idx_by_str)
        series.append(
            {
                "chapter": r.chapter,
                "chapter_title": chapter_titles.get(r.chapter, ""),
                "realm": realm,
                "realm_index": realm_idx_by_str.get(realm, None),
                "items_count": len((st.get("items") or [])),
                "skills_count": len((st.get("skills") or [])),
                "alive": st.get("alive", True),
                "note": r.note,
            }
        )
    return {
        "hero": {
            "id": hero.id,
            "name": hero.name,
            "description": hero.description,
            "importance": hero.importance,
        },
        "realm_levels": realm_idx_by_str,
        "series": series,
    }


# ---------------------------------------------------------------------------
# Character relationship graph
# ---------------------------------------------------------------------------

def character_graph(up_to_chapter: int | None = None, top_n: int = 60) -> dict[str, Any]:
    """Top-N person nodes with role + relationship-labeled edges.

    Edges come from two sources, in this order of priority:
      1. ``Relationship`` table (LLM-labeled) — each row produces a directed
         edge with a human-readable label. This is the *meaningful* layer.
      2. Co-occurrence fallback — weighted blend of plot/foreshadow/state
         co-mention. Only used to surface pairs the LLM didn't label, so the
         graph isn't sparse before relationship extraction has run.
    """

    with session_scope() as s:
        people = s.execute(
            select(Entity)
            .where(Entity.type == "person")
            .order_by(desc(Entity.importance))
            .limit(top_n)
        ).scalars().all()
        keep = {p.id: p for p in people}
        rels = s.execute(select(Relationship)).scalars().all()

        plot_q = select(PlotPoint)
        if up_to_chapter is not None:
            plot_q = plot_q.where(PlotPoint.chapter <= up_to_chapter)
        plots = s.execute(plot_q).scalars().all()

        fs_q = select(Foreshadowing)
        if up_to_chapter is not None:
            fs_q = fs_q.where(Foreshadowing.planted_chapter <= up_to_chapter)
        fs_rows = s.execute(fs_q).scalars().all()

        state_q = select(EntityState.entity_id, EntityState.chapter)
        if up_to_chapter is not None:
            state_q = state_q.where(EntityState.chapter <= up_to_chapter)
        state_rows = s.execute(state_q).all()

    # Count relationships per node for the "N 条关系" badge
    rel_count_by_id: dict[int, int] = defaultdict(int)
    pair_labeled: set[tuple[int, int]] = set()

    edges_out: list[dict[str, Any]] = []
    for r in rels:
        if r.from_entity_id not in keep or r.to_entity_id not in keep:
            continue
        rel_count_by_id[r.from_entity_id] += 1
        rel_count_by_id[r.to_entity_id] += 1
        a, b = sorted([r.from_entity_id, r.to_entity_id])
        pair_labeled.add((a, b))
        edges_out.append({
            "data": {
                "id": f"r{r.id}",
                "source": str(r.from_entity_id),
                "target": str(r.to_entity_id),
                "label": r.label,
                "description": r.description,
                "weight": r.weight or 1,
                "kind": "labeled",
                "status": r.status,
            }
        })

    # Co-occurrence fallback for pairs the LLM didn't label
    co_w: dict[tuple[int, int], int] = defaultdict(int)

    def _co(ids: list[int], weight: int) -> None:
        ids = sorted({eid for eid in ids if eid in keep})
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                co_w[(ids[i], ids[j])] += weight

    for p in plots:
        _co(list(p.involved_entity_ids_json or []), 2)
    for f in fs_rows:
        _co(list(f.related_entity_ids_json or []), 1)
    by_chapter: dict[int, list[int]] = defaultdict(list)
    for eid, ch in state_rows:
        if eid in keep:
            by_chapter[ch].append(eid)
    for ids in by_chapter.values():
        _co(ids, 1)

    for (a, b), w in co_w.items():
        if (a, b) in pair_labeled:
            continue
        if w < 2:
            continue  # filter weak fallback
        edges_out.append({
            "data": {
                "id": f"e{a}-{b}",
                "source": str(a),
                "target": str(b),
                "weight": w,
                "kind": "co_occur",
            }
        })

    return {
        "nodes": [
            {
                "data": {
                    "id": str(p.id),
                    "label": p.name[:18] + ("…" if len(p.name) > 18 else ""),
                    "full_name": p.name,
                    "importance": p.importance or 0,
                    "first_chapter": p.first_appear_chapter,
                    "description": (p.description or "")[:200],
                    "role": p.role or "minor",
                    "rel_count": rel_count_by_id.get(p.id, 0),
                }
            }
            for p in people
        ],
        "edges": edges_out,
    }


# ---------------------------------------------------------------------------
# Foreshadowing timeline
# ---------------------------------------------------------------------------

def foreshadow_graph(up_to_chapter: int | None = None) -> dict[str, Any]:
    """Return foreshadowings + corpus chapter range so the frontend can lay them
    out as a Gantt-style timeline (X = chapter index, one row per foreshadow,
    band from planted → resolved or planted → end-of-corpus for open ones)."""

    with session_scope() as s:
        q = select(Foreshadowing).order_by(asc(Foreshadowing.planted_chapter))
        if up_to_chapter is not None:
            q = q.where(Foreshadowing.planted_chapter <= up_to_chapter)
        rows = s.execute(q).scalars().all()
        max_chapter = s.execute(
            select(func.max(Chapter.number))
        ).scalar_one() or 0

    return {
        "max_chapter": max_chapter,
        "items": [
            {
                "id": r.id,
                "type": r.type,
                "status": r.status,
                "planted_chapter": r.planted_chapter,
                "resolved_chapter": r.resolved_chapter,
                "description": r.description,
                "resolved_description": r.resolved_description,
                "span": (r.resolved_chapter or max_chapter) - r.planted_chapter,
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Plot timeline
# ---------------------------------------------------------------------------

def timeline(min_importance: int = 50) -> list[dict[str, Any]]:
    with session_scope() as s:
        rows = s.execute(
            select(PlotPoint)
            .where(PlotPoint.importance >= min_importance)
            .order_by(PlotPoint.chapter)
        ).scalars().all()
        chapter_titles = dict(s.execute(select(Chapter.number, Chapter.title)).all())
    return [
        {
            "chapter": p.chapter,
            "chapter_title": chapter_titles.get(p.chapter, ""),
            "summary": p.summary,
            "importance": p.importance,
            "involved": p.involved_entity_ids_json or [],
        }
        for p in rows
    ]
