"""Multi-agent extraction over the corpus, 50 chapters per batch.

Five Haiku agents run sequentially per batch (could be parallelized later but
they share a common cached prefix — sequential lets us reuse the cache hit).
The cached system prefix carries:
  * existing entities (typed, with id + aliases)
  * open foreshadowings
  * known world rules
  * tracked key-entity names (for StateAgent)

Each agent's *user* turn carries only the chapter text — that's the changing part.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..books.library import active_paths
from ..config import BATCH_SIZE_CHAPTERS, MODEL_FAST
from ..db import session_scope
from ..llm import client as llm
from ..llm.prompts.extraction import all_agents
from ..memory.models import (
    Chapter,
    Entity,
    EntityState,
    ExtractionBatch,
    Foreshadowing,
    Mystery,
    PlotPoint,
    WorldRule,
)
from ..memory.schema_init import init_schema


def _load_corpus_text() -> str:
    p = active_paths()["corpus_txt"]
    if not p.exists():
        raise RuntimeError(
            f"no UTF-8 corpus at {p} — run /ingest/split first"
        )
    return p.read_text(encoding="utf-8")


def _build_cached_context(session) -> tuple[str, list[dict[str, Any]]]:
    """Return (entity-table-blob, list-of-cache-blocks)."""

    entities = session.execute(select(Entity)).scalars().all()
    open_fs = session.execute(
        select(Foreshadowing).where(Foreshadowing.status == "open")
    ).scalars().all()
    rules = session.execute(select(WorldRule)).scalars().all()
    # Mysteries that haven't been resolved/contradicted are the live "reader
    # questions" the MysteryAgent must avoid duplicating and should refine.
    live_mysteries = session.execute(
        select(Mystery).where(
            (Mystery.status == "open")
            | (Mystery.status == "sharpened")
            | (Mystery.status == "partially_resolved")
        )
    ).scalars().all()

    entity_dump = [
        {"id": e.id, "type": e.type, "name": e.name, "aliases": e.aliases_json or [],
         "description": (e.description or "")[:160]}
        for e in entities
    ]
    fs_dump = [
        {"id": f.id, "type": f.type, "planted_chapter": f.planted_chapter,
         "description": (f.description or "")[:200]}
        for f in open_fs
    ]
    world_dump = [{"term": r.term, "definition": (r.definition or "")[:200]} for r in rules]

    # Top-importance entities are the ones StateAgent should track.
    key_names = sorted(
        [e.name for e in entities if e.type == "person" and (e.importance or 0) >= 40]
    )

    blocks: list[dict[str, Any]] = []
    blocks.append(
        llm.cached_block(
            "现有实体表（JSON，按 type/name 排序）：\n"
            + llm.stable_json(entity_dump)
        )
    )
    blocks.append(
        llm.cached_block(
            "现有未收束伏笔表（JSON）：\n" + llm.stable_json(fs_dump)
        )
    )
    blocks.append(
        llm.cached_block(
            "现有世界规则表（JSON）：\n" + llm.stable_json(world_dump)
        )
    )
    blocks.append(
        llm.cached_block(
            "需要 StateAgent 跟踪的核心人物名（StateAgent 才会用到）：\n"
            + llm.stable_json(key_names)
        )
    )
    mystery_dump = [
        {
            "id": m.id,
            "category": m.category,
            "severity": m.severity,
            "status": m.status,
            "confidence": m.confidence,
            "question": m.question,
            "clues_so_far": list(m.clues_json or [])[-5:],  # last 5 to keep prompt bounded
        }
        for m in live_mysteries
    ]
    blocks.append(
        llm.cached_block(
            "现有 mysteries 表（MysteryAgent 才会用到 — 不要重复创建相似 question）：\n"
            + llm.stable_json(mystery_dump)
        )
    )
    return llm.stable_json(entity_dump), blocks


def _chapter_text(corpus: str, c: Chapter) -> str:
    return corpus[c.char_offset_start : c.char_offset_end]


def _name_to_entity_id(session, names: list[str]) -> list[int]:
    if not names:
        return []
    out: list[int] = []
    for n in names:
        e = session.execute(
            select(Entity).where(Entity.name == n).limit(1)
        ).scalar_one_or_none()
        if e:
            out.append(e.id)
    return out


def _persist_entities(session, items: list[dict[str, Any]]) -> None:
    max_chapter = session.execute(select(Chapter.number).order_by(Chapter.number.desc()).limit(1)).scalar_one_or_none()
    for it in items:
        if not isinstance(it, dict) or "name" not in it or "type" not in it:
            continue
        fac = it.get("first_appear_chapter")
        if isinstance(fac, int) and max_chapter is not None and fac > max_chapter:
            it["first_appear_chapter"] = max_chapter
        elif not isinstance(fac, int) or fac <= 0:
            it["first_appear_chapter"] = None
        existing_id = it.get("match_existing_id")
        if existing_id:
            ex = session.get(Entity, existing_id)
            if ex:
                aliases = set(ex.aliases_json or [])
                aliases.add(it["name"])
                ex.aliases_json = sorted(aliases)
                ex.importance = (ex.importance or 0) + 1
                continue
        # else create new (or no-op if exists by (type,name)).
        # Race-safe: under parallel workers another thread might insert the
        # same (type, name) between our SELECT and INSERT. Use a SAVEPOINT
        # so the IntegrityError doesn't poison the outer transaction.
        existing = session.execute(
            select(Entity).where(Entity.type == it["type"], Entity.name == it["name"]).limit(1)
        ).scalar_one_or_none()
        if existing:
            existing.importance = (existing.importance or 0) + 1
            continue
        e = Entity(
            type=it["type"],
            name=it["name"],
            aliases_json=it.get("aliases", []),
            first_appear_chapter=it.get("first_appear_chapter"),
            description=it.get("description", ""),
            importance=1,
        )
        try:
            with session.begin_nested():
                session.add(e)
                session.flush()
        except IntegrityError:
            session.expunge(e)
            existing = session.execute(
                select(Entity).where(Entity.type == it["type"], Entity.name == it["name"]).limit(1)
            ).scalar_one_or_none()
            if existing:
                existing.importance = (existing.importance or 0) + 1


def _persist_foreshadowings(session, planted: list[dict[str, Any]],
                             resolved: list[dict[str, Any]]) -> None:
    # Cap chapter values to what actually exists; the model occasionally
    # invents a chapter past the end of the book (e.g. 1473 for a 1472-chapter
    # novel) which would trip the chapters.number FK on planted/resolved.
    max_chapter = session.execute(select(Chapter.number).order_by(Chapter.number.desc()).limit(1)).scalar_one_or_none()

    def _valid_chapter(n: Any) -> int | None:
        if not isinstance(n, int) or n <= 0:
            return None
        if max_chapter is not None and n > max_chapter:
            return max_chapter  # clamp; the model meant "near the end"
        return n

    for p in planted:
        if not isinstance(p, dict):
            continue
        if not all(k in p for k in ("description", "planted_chapter", "type")):
            continue
        pc = _valid_chapter(p["planted_chapter"])
        if pc is None:
            continue
        ent_ids = _name_to_entity_id(session, p.get("related_entity_names", []))
        f = Foreshadowing(
            planted_chapter=pc,
            type=p["type"],
            description=p["description"],
            planted_excerpt=p.get("planted_excerpt"),
            status="open",
            related_entity_ids_json=ent_ids,
        )
        session.add(f)
    for r in resolved:
        if not isinstance(r, dict):
            continue
        if not all(k in r for k in ("foreshadow_id", "resolved_chapter")):
            continue
        rc = _valid_chapter(r["resolved_chapter"])
        if rc is None:
            continue
        f = session.get(Foreshadowing, r["foreshadow_id"])
        if not f:
            continue
        f.status = "resolved"
        f.resolved_chapter = rc
        f.resolved_description = r.get("resolved_description", "")


def _persist_states(session, items: list[dict[str, Any]]) -> None:
    items = [it for it in items if isinstance(it, dict) and it.get("entity_name")]
    items = sorted(items, key=lambda x: x.get("chapter", 0))
    max_chapter = session.execute(select(Chapter.number).order_by(Chapter.number.desc()).limit(1)).scalar_one_or_none()
    for it in items:
        ch = it.get("chapter")
        if not isinstance(ch, int) or ch <= 0:
            continue
        if max_chapter is not None and ch > max_chapter:
            it["chapter"] = max_chapter  # clamp
        session.flush()
        e = session.execute(
            select(Entity).where(Entity.name == it["entity_name"]).limit(1)
        ).scalar_one_or_none()
        if not e:
            continue
        prev = session.execute(
            select(EntityState)
            .where(EntityState.entity_id == e.id, EntityState.chapter < it["chapter"])
            .order_by(EntityState.chapter.desc())
            .limit(1)
        ).scalar_one_or_none()
        prev_state = (prev.state_json if prev else {}) or {}
        new_state = dict(prev_state)
        change = it.get("change", {}) or {}
        if "realm" in change and change["realm"]:
            new_state["realm"] = change["realm"]
        if change.get("items_gained"):
            new_state.setdefault("items", [])
            new_state["items"] = sorted(set((new_state["items"] or []) + change["items_gained"]))
        if change.get("items_lost"):
            new_state["items"] = [x for x in new_state.get("items", []) if x not in change["items_lost"]]
        if change.get("skills_gained"):
            new_state.setdefault("skills", [])
            new_state["skills"] = sorted(set((new_state["skills"] or []) + change["skills_gained"]))
        if "alive" in change:
            new_state["alive"] = change["alive"]
        s = EntityState(
            entity_id=e.id,
            chapter=it["chapter"],
            state_json=new_state,
            diff_json=change,
            note=change.get("note"),
        )
        session.add(s)


def _persist_plot(session, items: list[dict[str, Any]]) -> None:
    max_chapter = session.execute(select(Chapter.number).order_by(Chapter.number.desc()).limit(1)).scalar_one_or_none()
    for it in items:
        if not isinstance(it, dict) or "summary" not in it or "chapter" not in it:
            continue
        ch = it["chapter"]
        if not isinstance(ch, int) or ch <= 0:
            continue
        if max_chapter is not None and ch > max_chapter:
            ch = max_chapter
        ids = _name_to_entity_id(session, it.get("involved_entity_names", []))
        p = PlotPoint(
            chapter=ch,
            summary=it["summary"],
            importance=it.get("importance", 50),
            involved_entity_ids_json=ids,
        )
        session.add(p)


def _persist_mystery_actions(
    session,
    actions: list[dict[str, Any]],
    *,
    batch_id: int,
    chapter_range: tuple[int, int],
) -> None:
    """Apply MysteryAgent actions: create / update / resolve / contradict.

    Each action also appends an entry to the mystery's ``updates_log_json`` so
    the UI can render a per-mystery timeline showing how the question emerged
    and got refined across batches.
    """

    if not isinstance(actions, list):
        return
    chapter_end = chapter_range[1]

    for a in actions:
        if not isinstance(a, dict):
            continue
        kind = a.get("kind")
        summary = (a.get("summary") or "").strip()
        if kind not in {"create", "update", "resolve", "contradict"}:
            continue
        log_entry = {
            "batch_id": batch_id,
            "chapter_range": list(chapter_range),
            "change": kind if kind != "create" else "first_seen",
            "summary": summary[:160],
            "new_clue": (a.get("new_clue") or "")[:240] if a.get("new_clue") else None,
        }

        if kind == "create":
            if not a.get("question") or not a.get("category"):
                continue
            initial_clue = a.get("new_clue") or summary
            row = Mystery(
                question=a["question"],
                category=a["category"],
                severity=a.get("severity") or "major",
                why_it_matters=a.get("why_it_matters") or "",
                clues_json=[initial_clue] if initial_clue else [],
                related_entity_ids_json=list(a.get("related_entity_ids") or []),
                related_foreshadow_ids_json=list(a.get("related_foreshadow_ids") or []),
                source="auto",
                status="open",
                confidence=50,
                first_seen_batch_id=batch_id,
                last_updated_batch_id=batch_id,
                last_updated_chapter=chapter_end,
                updates_log_json=[log_entry],
            )
            session.add(row)
            continue

        # update / resolve / contradict
        mid = a.get("mystery_id")
        if not isinstance(mid, int):
            continue
        m = session.get(Mystery, mid)
        if not m:
            continue

        delta = a.get("confidence_delta")
        if not isinstance(delta, int):
            delta = {"update": 10, "resolve": 30, "contradict": -20}.get(kind, 0)
        new_confidence = max(0, min(100, (m.confidence or 50) + delta))

        if kind == "update":
            m.status = "sharpened" if (m.status or "open") == "open" else m.status
        elif kind == "resolve":
            m.status = "resolved"
        elif kind == "contradict":
            m.status = "contradicted"

        m.confidence = new_confidence
        m.last_updated_batch_id = batch_id
        m.last_updated_chapter = chapter_end

        clues = list(m.clues_json or [])
        if a.get("new_clue"):
            clues.append(a["new_clue"][:240])
        m.clues_json = clues

        # merge related ids into existing sets without dedup losing order
        for field, key in (("related_entity_ids_json", "related_entity_ids"),
                           ("related_foreshadow_ids_json", "related_foreshadow_ids")):
            existing_ids = list(getattr(m, field) or [])
            for nid in (a.get(key) or []):
                if isinstance(nid, int) and nid not in existing_ids:
                    existing_ids.append(nid)
            setattr(m, field, existing_ids)

        log = list(m.updates_log_json or [])
        log.append(log_entry)
        m.updates_log_json = log


def _persist_world(session, items: list[dict[str, Any]]) -> None:
    max_chapter = session.execute(select(Chapter.number).order_by(Chapter.number.desc()).limit(1)).scalar_one_or_none()
    for it in items:
        if not isinstance(it, dict) or "term" not in it or "definition" not in it:
            continue
        existing = session.execute(
            select(WorldRule).where(WorldRule.term == it["term"]).limit(1)
        ).scalar_one_or_none()
        if existing:
            continue
        fc = it.get("first_chapter")
        if isinstance(fc, int) and max_chapter is not None and fc > max_chapter:
            fc = max_chapter
        elif not isinstance(fc, int) or fc <= 0:
            fc = None  # FK column is nullable
        rule = WorldRule(
            term=it["term"],
            definition=it["definition"],
            first_chapter=fc,
        )
        try:
            with session.begin_nested():
                session.add(rule)
                session.flush()
        except IntegrityError:
            # Another worker inserted this term between our SELECT and our INSERT.
            session.expunge(rule)


def _extract_loads_json(s: str) -> dict[str, Any]:
    """Parse a JSON object out of model text (strip fences, repair)."""
    import json
    import re
    s = re.sub(r"```json|```", "", s or "").strip()
    try:
        return json.loads(s)
    except Exception:
        try:
            from json_repair import repair_json
            d = json.loads(repair_json(s))
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}


def _agent_call(*, name: str, system_blocks: list[dict[str, Any]], user_text: str,
                tool: dict[str, Any], system_text: str) -> tuple[dict[str, Any], float]:
    sys_blocks = [{"type": "text", "text": system_text}, *system_blocks]
    # Happy path: forced tool_choice. Works first-try on small/medium context.
    try:
        resp = llm.call(
            agent=f"extract.{name}",
            model=MODEL_FAST,
            system=sys_blocks,
            messages=[{"role": "user", "content": user_text}],
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            max_tokens=4096,
            temperature=0.2,
        )
        if resp.tool_use:
            return resp.tool_use["input"], resp.cost_usd
        # Non-empty content but no tool call — try to parse JSON from content.
        if (resp.text or "").strip():
            parsed = _extract_loads_json(resp.text)
            if parsed:
                return parsed, resp.cost_usd
    except Exception:  # noqa: BLE001
        # Empty after retries — typically a volc reasoning model dropping the
        # tool output on large context (改进记录 #14). Fall through to JSON-in-text.
        pass

    # Fallback: JSON-in-text — reliable when forced tool_choice silently fails on
    # large context. Embed the tool's schema; no tools; repair-parse the content.
    import json as _json
    hint = ("\n\n# 输出格式（严格 · 覆盖前述任何「调用工具」指示）\n"
            "只输出一个 JSON 对象，不要任何其它文字、不要 markdown 围栏。必须严格符合此 JSON Schema：\n"
            + _json.dumps(tool.get("input_schema", {}), ensure_ascii=False))
    resp2 = llm.call(
        agent=f"extract.{name}",
        model=MODEL_FAST,
        system=[{"type": "text", "text": system_text + hint}, *system_blocks],
        messages=[{"role": "user", "content": user_text}],
        max_tokens=8000,
        temperature=0.2,
    )
    return _extract_loads_json(resp2.text), resp2.cost_usd


def run_batch(start: int, end: int) -> dict[str, Any]:
    """Extract all signals from chapters in [start, end)."""

    init_schema()
    corpus = _load_corpus_text()

    with session_scope() as s:
        chapters = (
            s.execute(
                select(Chapter)
                .where(Chapter.number >= start, Chapter.number < end)
                .order_by(Chapter.number)
            )
            .scalars()
            .all()
        )
        if not chapters:
            raise RuntimeError(f"no chapters in [{start},{end})")

        batch = ExtractionBatch(
            chapter_start=start, chapter_end=end, status="running"
        )
        s.add(batch)
        s.flush()
        batch_id = batch.id

    # Build the user content (chapter text concatenated).
    pieces = []
    for c in chapters:
        body = corpus[c.char_offset_start : c.char_offset_end]
        pieces.append(f"\n\n=== {c.title} (第{c.number}章) ===\n{body}")
    user_text = (
        f"以下是第 {start} 到 {end - 1} 章的原文。请按你的职责完成抽取。\n"
        + "".join(pieces)
    )

    agents = all_agents()
    total_cost = 0.0
    # Each agent gets: (1) read context in its own session, (2) call LLM with
    # NO open transaction (so the audit-table writer in llm.client can land),
    # (3) persist results in another session. This avoids SQLite write-write
    # contention that occurred when the audit INSERT collided with a long-held
    # outer transaction.
    chapter_range = (start, end - 1)

    def _persist_for(name: str, s, out: dict) -> None:
        if name == "entity":
            _persist_entities(s, out.get("entities", []))
        elif name == "foreshadow":
            _persist_foreshadowings(s, out.get("planted", []), out.get("resolved", []))
        elif name == "state":
            _persist_states(s, out.get("states", []))
        elif name == "plot":
            _persist_plot(s, out.get("plot_points", []))
        elif name == "world":
            _persist_world(s, out.get("rules", []))
        elif name == "mystery":
            _persist_mystery_actions(
                s,
                out.get("actions", []),
                batch_id=batch_id,
                chapter_range=chapter_range,
            )

    try:
        # mystery agent runs LAST so it can reference whatever entity / fs /
        # plot rows the previous five just wrote.
        for name in ["entity", "foreshadow", "state", "plot", "world", "mystery"]:
            # Refresh cached context — earlier agent writes must be visible to
            # later agents (especially mystery, which references them).
            with session_scope() as s:
                _, sys_blocks = _build_cached_context(s)

            out, cost = _agent_call(
                name=name,
                system_blocks=sys_blocks,
                user_text=user_text,
                tool=agents[name]["tool"],
                system_text=agents[name]["system"],
            )
            total_cost += cost

            with session_scope() as s:
                _persist_for(name, s, out)

        with session_scope() as s:
            b = s.get(ExtractionBatch, batch_id)
            if b:
                b.status = "done"
                b.cost_usd = total_cost
                b.finished_at = datetime.utcnow()

        return {"batch_id": batch_id, "status": "done", "cost_usd": total_cost}

    except Exception as exc:  # noqa: BLE001
        # Mark failed so the batch never hangs in "running" (which would make
        # run_all skip its range forever). Guard against a missing row so this
        # handler can't itself crash and mask the original exception.
        with session_scope() as s:
            b = s.get(ExtractionBatch, batch_id)
            if b:
                b.status = "failed"
                b.error = str(exc)[:1000]
                b.finished_at = datetime.utcnow()
        raise


def _persist_dispatch(name: str, s, out: dict, *, batch_id: int, chapter_range) -> None:
    if name == "entity":
        _persist_entities(s, out.get("entities", []))
    elif name == "foreshadow":
        _persist_foreshadowings(s, out.get("planted", []), out.get("resolved", []))
    elif name == "state":
        _persist_states(s, out.get("states", []))
    elif name == "plot":
        _persist_plot(s, out.get("plot_points", []))
    elif name == "world":
        _persist_world(s, out.get("rules", []))
    elif name == "mystery":
        _persist_mystery_actions(s, out.get("actions", []), batch_id=batch_id, chapter_range=chapter_range)


def extract_one_chapter(chapter_index: int, text: str) -> dict[str, Any]:
    """写→回灌记忆反馈环 (A)：增量抽取**单个已生成章节**的记忆，使后续章节的
    上下文能"读到"刚写出来的新章节（实体/伏笔/状态/世界规则/疑点）。

    复用同一套 6-agent 抽取，但读的是原始正文（不是 corpus 偏移）。Best-effort：
    任何失败都标 batch failed 并抛出，但调用方应吞掉异常（不拖垮成稿）。
    """
    init_schema()
    text = (text or "").strip()
    if not text:
        return {"status": "skipped", "reason": "empty"}
    user_text = (f"以下是第 {chapter_index} 章的正文（新续写出的章节）。"
                 f"请按你的职责从中抽取结构化信息。\n\n{text}")
    agents = all_agents()
    # Idempotent: reuse the batch row if this chapter was extracted before
    # (re-runs / resume / re-write) — the UNIQUE(chapter_start,chapter_end) would
    # otherwise blow up on a fresh insert. Entity/world persists already upsert.
    with session_scope() as s:
        batch = s.execute(
            select(ExtractionBatch).where(
                ExtractionBatch.chapter_start == chapter_index,
                ExtractionBatch.chapter_end == chapter_index + 1,
            ).limit(1)
        ).scalar_one_or_none()
        if batch is None:
            batch = ExtractionBatch(chapter_start=chapter_index, chapter_end=chapter_index + 1,
                                    status="running")
            s.add(batch); s.flush()
        else:
            batch.status = "running"; batch.error = None; batch.finished_at = None
        batch_id = batch.id
    chapter_range = (chapter_index, chapter_index)
    total_cost = 0.0
    try:
        for name in ["entity", "foreshadow", "state", "plot", "world", "mystery"]:
            with session_scope() as s:
                _, sys_blocks = _build_cached_context(s)
            out, cost = _agent_call(name=name, system_blocks=sys_blocks, user_text=user_text,
                                    tool=agents[name]["tool"], system_text=agents[name]["system"])
            total_cost += cost
            with session_scope() as s:
                _persist_dispatch(name, s, out, batch_id=batch_id, chapter_range=chapter_range)
        with session_scope() as s:
            b = s.get(ExtractionBatch, batch_id)
            if b:
                b.status = "done"; b.cost_usd = total_cost; b.finished_at = datetime.utcnow()
        return {"status": "done", "chapter": chapter_index, "cost_usd": total_cost}
    except Exception as exc:  # noqa: BLE001
        with session_scope() as s:
            b = s.get(ExtractionBatch, batch_id)
            if b:
                b.status = "failed"; b.error = str(exc)[:500]; b.finished_at = datetime.utcnow()
        raise


def run_all(
    *,
    batch_size: int = BATCH_SIZE_CHAPTERS,
    max_batches: int | None = None,
    workers: int = 1,
) -> None:
    """Process all unfinished batches.

    With ``workers > 1`` batches run in parallel via a thread pool. Each batch
    is still 5 sequential agents (later agents need earlier ones' entity-table
    output) — only across-batch parallelism is exposed. The work is
    network-bound (LLM API), so threads beat processes here: shared engine,
    shared OpenAI client, no fork overhead.

    Cross-batch races are bounded:
      * (type, name) entity collisions: SAVEPOINT in ``_persist_entities``
      * world rule term collisions: SAVEPOINT in ``_persist_world``
      * extraction_batches uniqueness: enforced by pre-computed work queue
    """

    init_schema()
    with session_scope() as s:
        all_chapters = s.execute(
            select(Chapter.number).order_by(Chapter.number)
        ).scalars().all()
    if not all_chapters:
        print("no chapters — run split first")
        return
    lo, hi = all_chapters[0], all_chapters[-1] + 1

    # Pre-compute the work queue. Skip any range that *overlaps* with an
    # already-done OR currently-running batch — different batch_size requests
    # otherwise produce overlapping ranges (e.g. (1,51) running while
    # (1,6),(6,11)... get queued) and race on entity-table writes.
    with session_scope() as s:
        existing = [
            (b.chapter_start, b.chapter_end, b.status)
            for b in s.execute(
                select(ExtractionBatch).where(
                    ExtractionBatch.status.in_(["done", "running", "pending"])
                )
            ).scalars()
        ]

    def _overlaps(a_start: int, a_end: int) -> tuple[str, tuple[int, int]] | None:
        for s_, e_, st in existing:
            if a_start < e_ and s_ < a_end:
                return st, (s_, e_)
        return None

    todo: list[tuple[int, int]] = []
    for start in range(lo, hi, batch_size):
        end = min(start + batch_size, hi)
        hit = _overlaps(start, end)
        if hit is not None:
            print(f"[skip] {start}-{end} overlaps with {hit[0]} batch {hit[1]}")
        else:
            todo.append((start, end))
    if max_batches is not None:
        todo = todo[:max_batches]
    if not todo:
        print("nothing to do")
        return

    if workers <= 1:
        for start, end in todo:
            print(f"[run]  {start}-{end}")
            try:
                print(f"       {run_batch(start, end)}")
            except Exception as exc:  # noqa: BLE001
                print(f"       FAIL {start}-{end}: {exc}")
        return

    print(f"[parallel] {len(todo)} batches × {workers} workers")
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="batch") as exe:
        futs = {exe.submit(run_batch, s, e): (s, e) for s, e in todo}
        for fut in as_completed(futs):
            start, end = futs[fut]
            try:
                info = fut.result()
                print(f"[done] {start}-{end}: {info}")
            except Exception as exc:  # noqa: BLE001
                print(f"[FAIL] {start}-{end}: {exc}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=int)
    p.add_argument("--end", type=int)
    p.add_argument("--batches", type=int, help="run all, but stop after this many batches")
    p.add_argument("--workers", type=int, default=1,
                   help="parallel batch workers (each batch's 5 agents stay sequential)")
    args = p.parse_args()
    if args.start is not None and args.end is not None:
        info = run_batch(args.start, args.end)
        print(info)
    else:
        run_all(max_batches=args.batches, workers=args.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
