"""Retrospective MysteryAgent rebuild over already-extracted batches.

For users who already paid to extract entity/foreshadow/state/plot/world over
the whole novel: this endpoint walks through ``status='done'`` batches in
chapter order and *only* runs MysteryAgent on each. The other 5 agents are NOT
re-run — their outputs already exist in the DB.

Result: each existing batch effectively gets its 6th agent applied
retroactively, producing the same incremental mystery lifecycle the future-
extraction path will produce naturally.

Resume-friendly: skips batches whose ``last_processed_for_mysteries`` flag is
set (we use ``ExtractionBatch.error`` as a no-op marker — see notes below).
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import asc, delete, select

from ..config import MODEL_FAST
from ..db import session_scope
from ..ingest.extract import (
    _agent_call,
    _build_cached_context,
    _load_corpus_text,
    _persist_mystery_actions,
)
from ..llm.prompts.extraction import all_agents
from ..memory.models import (
    Chapter,
    ExtractionBatch,
    Foreshadowing,
    Mystery,
    PlotPoint,
)


def _batch_summary_text(corpus: str, batch_id: int, start: int, end: int) -> str:
    """Build the user prompt for retrospective MysteryAgent run.

    To keep token cost bounded, we DON'T re-feed the raw 50 chapters of text
    (that's already what the original extraction agents saw). Instead we feed
    the *structured outputs* the prior agents produced, plus the chapter range
    metadata. The cached prefix already carries entity/foreshadow/world tables.
    """

    with session_scope() as s:
        plots = s.execute(
            select(PlotPoint).where(
                PlotPoint.chapter >= start,
                PlotPoint.chapter <= end,
            )
        ).scalars().all()
        fs_planted = s.execute(
            select(Foreshadowing).where(
                Foreshadowing.planted_chapter >= start,
                Foreshadowing.planted_chapter <= end,
            )
        ).scalars().all()
        fs_resolved = s.execute(
            select(Foreshadowing).where(
                Foreshadowing.resolved_chapter >= start,
                Foreshadowing.resolved_chapter <= end,
            )
        ).scalars().all()

    plot_dump = [
        {"ch": p.chapter, "imp": p.importance, "summary": (p.summary or "")[:200]}
        for p in plots
    ]
    fs_planted_dump = [
        {"id": f.id, "type": f.type, "ch": f.planted_chapter, "desc": (f.description or "")[:160]}
        for f in fs_planted
    ]
    fs_resolved_dump = [
        {
            "id": f.id, "type": f.type,
            "planted_ch": f.planted_chapter, "resolved_ch": f.resolved_chapter,
            "resolution": (f.resolved_description or "")[:160],
        }
        for f in fs_resolved
    ]

    import json

    body = (
        f"# 第 {start}–{end} 章批次回顾（不含原文）\n\n"
        f"## 本批新增/收束的剧情节点\n{json.dumps(plot_dump, ensure_ascii=False, indent=1)}\n\n"
        f"## 本批埋下的伏笔\n{json.dumps(fs_planted_dump, ensure_ascii=False, indent=1)}\n\n"
        f"## 本批回应/收束的旧伏笔\n{json.dumps(fs_resolved_dump, ensure_ascii=False, indent=1)}\n\n"
        "请基于以上结构化信息（结合 system 中已积累的实体/伏笔/规则/现有 mysteries 表），"
        "对宏观疑点做必要的 create/update/resolve/contradict。早期批次以 create 为主，"
        "后期批次以 update/resolve 为主。"
    )
    return body


def rebuild(skip_existing: bool = False) -> dict[str, Any]:
    """Run MysteryAgent retroactively over all done batches in chapter order.

    Args:
        skip_existing: if True, skip batches that already appear in any mystery's
            ``updates_log_json`` (resume-friendly). If False (default), wipe all
            ``source='auto'`` mysteries and start fresh.
    """

    t0 = time.perf_counter()
    corpus = _load_corpus_text()  # cached helper; mystery prompt doesn't actually use it
    agents = all_agents()
    mystery_def = agents["mystery"]

    if not skip_existing:
        with session_scope() as s:
            s.execute(delete(Mystery).where(Mystery.source == "auto"))

    # Collect batches in chapter order.
    with session_scope() as s:
        batches = s.execute(
            select(ExtractionBatch)
            .where(ExtractionBatch.status == "done")
            .order_by(asc(ExtractionBatch.chapter_start))
        ).scalars().all()
        batch_list = [
            {
                "id": b.id,
                "start": b.chapter_start,
                "end": b.chapter_end - 1,
            }
            for b in batches
        ]

    # If skip_existing, build a set of batch_ids already touched.
    already: set[int] = set()
    if skip_existing:
        with session_scope() as s:
            for m in s.execute(select(Mystery)).scalars().all():
                for entry in (m.updates_log_json or []):
                    bid = entry.get("batch_id") if isinstance(entry, dict) else None
                    if isinstance(bid, int):
                        already.add(bid)

    total_cost = 0.0
    actions_per_batch: list[dict[str, Any]] = []

    for b in batch_list:
        if skip_existing and b["id"] in already:
            continue
        # Refresh cached context for THIS batch's view.
        with session_scope() as s:
            _, sys_blocks = _build_cached_context(s)

        user_text = _batch_summary_text(corpus, b["id"], b["start"], b["end"])
        try:
            out, cost = _agent_call(
                name="mystery",
                system_blocks=sys_blocks,
                user_text=user_text,
                tool=mystery_def["tool"],
                system_text=mystery_def["system"],
            )
        except Exception as exc:  # noqa: BLE001
            actions_per_batch.append({"batch_id": b["id"], "error": str(exc)[:200]})
            continue
        total_cost += cost

        actions = out.get("actions", []) if isinstance(out, dict) else []
        if not isinstance(actions, list):
            actions = []
        actions_per_batch.append(
            {"batch_id": b["id"], "range": [b["start"], b["end"]], "n_actions": len(actions)}
        )

        with session_scope() as s:
            _persist_mystery_actions(
                s,
                actions,
                batch_id=b["id"],
                chapter_range=(b["start"], b["end"]),
            )

    elapsed_s = round(time.perf_counter() - t0, 2)
    with session_scope() as s:
        n_total = s.execute(select(Mystery)).scalars().all()

    return {
        "batches_processed": len([x for x in actions_per_batch if "error" not in x]),
        "batches_failed": len([x for x in actions_per_batch if "error" in x]),
        "mysteries_total": len(n_total),
        "cost_usd": round(total_cost, 5),
        "elapsed_s": elapsed_s,
        "per_batch": actions_per_batch,
    }


# ---------------------------------------------------------------------------
# Read-side helpers (replace what discover.py used to expose)
# ---------------------------------------------------------------------------

def list_all() -> list[dict[str, Any]]:
    severity_order = {"core": 0, "major": 1, "minor": 2}
    status_order = {"open": 0, "sharpened": 1, "partially_resolved": 2,
                    "contradicted": 3, "resolved": 4}
    with session_scope() as s:
        rows = s.execute(select(Mystery)).scalars().all()
    rows_sorted = sorted(
        rows,
        key=lambda r: (
            status_order.get(r.status or "open", 99),
            severity_order.get(r.severity or "major", 99),
            -(r.confidence or 0),
            r.category or "z",
        ),
    )
    return [
        {
            "id": r.id,
            "question": r.question,
            "category": r.category,
            "severity": r.severity,
            "status": r.status,
            "confidence": r.confidence,
            "why_it_matters": r.why_it_matters,
            "clues": r.clues_json or [],
            "related_entity_ids": r.related_entity_ids_json or [],
            "related_foreshadow_ids": r.related_foreshadow_ids_json or [],
            "first_seen_batch_id": r.first_seen_batch_id,
            "last_updated_batch_id": r.last_updated_batch_id,
            "last_updated_chapter": r.last_updated_chapter,
            "updates_log": r.updates_log_json or [],
            "source": r.source,
            "note": r.note,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows_sorted
    ]


def delete_one(mystery_id: int) -> bool:
    with session_scope() as s:
        row = s.get(Mystery, mystery_id)
        if not row:
            return False
        s.delete(row)
    return True


def update_note(mystery_id: int, note: str) -> bool:
    with session_scope() as s:
        row = s.get(Mystery, mystery_id)
        if not row:
            return False
        row.note = note
    return True
