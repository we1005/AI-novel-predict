"""Outline refinement pipeline.

Single-stage LLM call. Input is one phase from an arc (or a single predict
candidate's range), plus the global cached context (entities/foreshadows/
mysteries/world rules). Output is a chapter-by-chapter outline.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select

from ..config import MODEL_STRONG
from ..db import session_scope
from ..llm import client as llm
from ..llm.prompts.outline_refine import OUTLINE_REFINE_SYSTEM, OUTLINE_REFINE_TOOL
from ..memory.models import ArcRun, OutlineRun, PredictionRun
from ..predict.pipeline import _ctx_blocks, _gather_context


def _coerce_list(v: Any) -> list:
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            decoded = json.loads(v)
            if isinstance(decoded, list):
                return decoded
        except json.JSONDecodeError:
            try:
                from json_repair import repair_json

                decoded = json.loads(repair_json(v))
                if isinstance(decoded, list):
                    return decoded
            except Exception:
                pass
    return []


def _resolve_source(source_kind: str, source_run_id: int, chosen_index: int,
                    phase_index: int | None) -> dict[str, Any]:
    """Pull the source candidate (an arc phase, or a predict candidate's text)
    and shape it into the prompt-ready dict."""

    with session_scope() as s:
        if source_kind == "arc":
            run = s.get(ArcRun, source_run_id)
            if not run:
                raise ValueError(f"no ArcRun id={source_run_id}")
            cands = _coerce_list(run.candidates_json)
            if chosen_index < 0 or chosen_index >= len(cands):
                raise ValueError(f"chosen_index {chosen_index} out of range")
            arc = cands[chosen_index] if isinstance(cands[chosen_index], dict) else {}
            phases = _coerce_list(arc.get("phases", []))
            if phase_index is None:
                raise ValueError("phase_index required for arc source")
            if phase_index < 0 or phase_index >= len(phases):
                raise ValueError(f"phase_index {phase_index} out of range")
            phase = phases[phase_index] if isinstance(phases[phase_index], dict) else {}
            return {
                "after_chapter": run.after_chapter,
                "user_hints": run.user_hints,
                "arc_meta": {
                    "title": arc.get("title"),
                    "theme": arc.get("theme"),
                    "tone": arc.get("tone"),
                    "world_truth": arc.get("world_truth"),
                    "protagonist_truth": arc.get("protagonist_truth"),
                    "ultimate_mastermind": arc.get("ultimate_mastermind"),
                },
                "phase": phase,
                "phase_index": phase_index,
                "phase_name": phase.get("name"),
                "chapter_start": phase.get("chapter_start"),
                "chapter_end": phase.get("chapter_end"),
            }

        if source_kind == "predict":
            run = s.get(PredictionRun, source_run_id)
            if not run:
                raise ValueError(f"no PredictionRun id={source_run_id}")
            cands = run.candidates_json or []
            if chosen_index < 0 or chosen_index >= len(cands):
                raise ValueError(f"chosen_index {chosen_index} out of range")
            cand = cands[chosen_index] if isinstance(cands[chosen_index], dict) else {}
            # /predict's candidate doesn't have a chapter range. Default to
            # the next 3 chapters after the user's after_chapter.
            cs = run.after_chapter + 1
            ce = run.after_chapter + 3
            return {
                "after_chapter": run.after_chapter,
                "user_hints": None,
                "arc_meta": None,
                "phase": {
                    "name": cand.get("title", "近期走向"),
                    "summary": cand.get("synopsis"),
                    "key_events": cand.get("uses_foreshadow_ids", []),
                },
                "phase_index": 0,
                "phase_name": cand.get("title", "近期走向"),
                "chapter_start": cs,
                "chapter_end": ce,
            }

        raise ValueError(f"unknown source_kind={source_kind!r}")


def refine(*, source_kind: str, source_run_id: int, chosen_index: int,
           phase_index: int | None = None,
           user_hints: str = "",
           chapter_start_override: int | None = None,
           chapter_end_override: int | None = None,
           continuity_hint: str | None = None,
           persist: bool = True) -> dict[str, Any]:
    src = _resolve_source(source_kind, source_run_id, chosen_index, phase_index)

    after_chapter = src["after_chapter"]
    # Whole-book projection drives clean, re-anchored ranges so the arc's
    # garbled-tail phase ranges (end<start, gaps) never reach the model.
    chapter_start = chapter_start_override if chapter_start_override is not None else src["chapter_start"]
    chapter_end = chapter_end_override if chapter_end_override is not None else src["chapter_end"]
    if continuity_hint:
        user_hints = (user_hints + "\n\n【承接上一阶段结尾】\n" + continuity_hint).strip()
    if chapter_start is None or chapter_end is None:
        raise ValueError("source did not provide a chapter range")

    ctx = _gather_context(after_chapter)
    blocks = _ctx_blocks(ctx)

    # JSON-in-text, not forced tool_choice: outline uses the same ~89k-char
    # context as predict/arc, where doubao-code's forced tool_choice silently
    # returns empty tool_calls + empty content (改进记录 #14). Embed the schema
    # and let the existing json_repair fallback parse it.
    _outline_hint = (
        "\n\n# 输出格式（严格 · 覆盖前述任何「调用工具」指示）\n"
        "只输出一个 JSON 对象，不要任何其它文字、不要 markdown 围栏。必须严格符合此 JSON Schema：\n"
        + json.dumps(OUTLINE_REFINE_TOOL["input_schema"], ensure_ascii=False)
    )
    system_chain: list[Any] = [{"type": "text", "text": OUTLINE_REFINE_SYSTEM + _outline_hint}, *blocks]
    combined_hints = "\n".join([h for h in [src.get("user_hints"), user_hints] if h]).strip()
    if combined_hints:
        system_chain.append({
            "type": "text",
            "text": "【创作偏好】\n" + combined_hints,
        })
    if src.get("arc_meta"):
        system_chain.append({
            "type": "text",
            "text": "【全弧元信息（不可违背）】\n" + llm.stable_json(src["arc_meta"]),
        })

    user = (
        f"# 任务\n\n"
        f"为 phase「{src['phase_name']}」（章节范围 {chapter_start}–{chapter_end}，"
        f"约 {chapter_end - chapter_start + 1} 章）生成逐章大纲。\n\n"
        f"# Phase 元信息\n\n"
        + llm.stable_json(src["phase"])
        + "\n\n请严格按 phase 范围输出 chapter_index 递增的章节大纲。"
    )

    resp = llm.call(
        agent="outline.refine",
        model=MODEL_STRONG,
        system=system_chain,
        messages=[{"role": "user", "content": user}],
        max_tokens=12000,
        temperature=0.6,
    )
    chapters_raw = (resp.tool_use or {}).get("input", {}).get("chapters", [])
    chapters = _coerce_list(chapters_raw)
    if not chapters and resp.text:
        try:
            from json_repair import repair_json

            decoded = json.loads(repair_json(resp.text))
            if isinstance(decoded, dict) and "chapters" in decoded:
                chapters = _coerce_list(decoded["chapters"])
            elif isinstance(decoded, list):
                chapters = decoded
        except Exception:
            pass

    # Filter out items that lost critical fields.
    chapters = [
        c for c in chapters
        if isinstance(c, dict) and isinstance(c.get("chapter_index"), int)
        and c.get("title") and c.get("must_include")
    ]
    chapters.sort(key=lambda c: c["chapter_index"])

    if not persist:
        # Whole-book projection aggregates phases itself; don't spam OutlineRun list.
        return {
            "id": None, "source_kind": source_kind, "source_run_id": source_run_id,
            "source_chosen_index": chosen_index, "phase_index": phase_index or 0,
            "phase_name": src.get("phase_name"), "chapter_start": chapter_start,
            "chapter_end": chapter_end, "chapters": chapters,
            "cost_usd": resp.cost_usd, "elapsed_ms": resp.elapsed_ms,
        }

    with session_scope() as s:
        row = OutlineRun(
            source_kind=source_kind,
            source_run_id=source_run_id,
            source_chosen_index=chosen_index,
            phase_index=phase_index if phase_index is not None else 0,
            phase_name=src.get("phase_name"),
            chapter_start=chapter_start,
            chapter_end=chapter_end,
            chapters_json=chapters,
            user_hints=combined_hints or None,
            cost_usd=resp.cost_usd,
            created_at=datetime.utcnow(),
        )
        s.add(row)
        s.flush()
        return {
            "id": row.id,
            "source_kind": source_kind,
            "source_run_id": source_run_id,
            "source_chosen_index": chosen_index,
            "phase_index": row.phase_index,
            "phase_name": row.phase_name,
            "chapter_start": chapter_start,
            "chapter_end": chapter_end,
            "chapters": chapters,
            "cost_usd": resp.cost_usd,
            "elapsed_ms": resp.elapsed_ms,
        }


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    with session_scope() as s:
        rows = s.execute(
            select(OutlineRun).order_by(desc(OutlineRun.id)).limit(limit)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "source_kind": r.source_kind,
                "source_run_id": r.source_run_id,
                "source_chosen_index": r.source_chosen_index,
                "phase_index": r.phase_index,
                "phase_name": r.phase_name,
                "chapter_start": r.chapter_start,
                "chapter_end": r.chapter_end,
                "chapter_count": len(r.chapters_json or []),
                "cost_usd": r.cost_usd,
                "user_hints": r.user_hints,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


def get_run(run_id: int) -> dict | None:
    with session_scope() as s:
        r = s.get(OutlineRun, run_id)
        if not r:
            return None
        return {
            "id": r.id,
            "source_kind": r.source_kind,
            "source_run_id": r.source_run_id,
            "source_chosen_index": r.source_chosen_index,
            "phase_index": r.phase_index,
            "phase_name": r.phase_name,
            "chapter_start": r.chapter_start,
            "chapter_end": r.chapter_end,
            "chapters": r.chapters_json or [],
            "user_hints": r.user_hints,
            "cost_usd": r.cost_usd,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }


def update_chapter(run_id: int, chapter_index: int, patch: dict) -> bool:
    """In-place edit one chapter's outline. ``patch`` is a partial dict of
    fields to merge into the existing chapter outline."""

    with session_scope() as s:
        r = s.get(OutlineRun, run_id)
        if not r:
            return False
        chapters = list(r.chapters_json or [])
        for i, c in enumerate(chapters):
            if isinstance(c, dict) and c.get("chapter_index") == chapter_index:
                merged = {**c, **{k: v for k, v in patch.items() if v is not None}}
                chapters[i] = merged
                r.chapters_json = chapters
                return True
    return False
