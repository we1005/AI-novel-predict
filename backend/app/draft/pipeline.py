"""Chapter writing pipeline: Writer + 3 reviewers (parallel) + Editor + ReAct.

The high-level loop:

    for attempt in 1..max_attempts:
        prose <- Writer(outline + style_refs + previous_attempt_feedback)
        if skip_reviews: return prose

        run StyleReviewer / PlotReviewer / ConsistencyReviewer in parallel
        editor_result <- Editor(reviews, attempt, max_attempts)

        if editor.decision == "approve" or "ship_with_warnings": break
        else continue with revision_brief

The four agents share the cached context from ``predict.pipeline._gather_context``
so we get cache hits across all 4 LLM calls per attempt.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select

from ..config import MODEL_FAST, MODEL_STRONG
from ..db import session_scope
from ..llm import client as llm
from ..llm.prompts.reviewers import (
    CONSISTENCY_REVIEWER_SYSTEM,
    CONSISTENCY_REVIEWER_TOOL,
    EDITOR_SYSTEM,
    EDITOR_TOOL,
    PLOT_REVIEWER_SYSTEM,
    PLOT_REVIEWER_TOOL,
    STYLE_REVIEWER_SYSTEM,
    STYLE_REVIEWER_TOOL,
    heuristic_decision,
)
from ..llm.prompts.writer import WRITER_SYSTEM, build_writer_user_message
from ..memory import fts as fts_recall
from ..memory.models import ChapterDraft, OutlineRun
from ..predict.pipeline import _ctx_blocks, _gather_context


def _coerce_dict(v: Any) -> dict:
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            d = json.loads(v)
            if isinstance(d, dict):
                return d
        except json.JSONDecodeError:
            try:
                from json_repair import repair_json
                d = json.loads(repair_json(v))
                if isinstance(d, dict):
                    return d
            except Exception:
                pass
    return {}


def _gather_style_refs(*, after_chapter: int, must_include: list[str]) -> list[dict]:
    """7-8 style anchor snippets: the 5 most recent chapters' bodies (truncated)
    plus 2-3 topic-relevant historical hits via FTS."""

    refs: list[dict] = []
    # Most-recent: pull last 5 chapters via FTS-style query (chapter range).
    # FTS doesn't have "by chapter" trivially, so we use a simple query.
    # Skip if we can't reasonably do it.
    try:
        recent = fts_recall.search(
            query="林云",  # almost always present in the protagonist novel
            limit=5,
            before_chapter=after_chapter + 1,
        )
        refs.extend(recent)
    except Exception:
        pass
    # Topic-relevant: use must_include phrases as queries.
    for phrase in (must_include or [])[:3]:
        if not phrase or len(phrase) < 4:
            continue
        try:
            hits = fts_recall.search(query=phrase[:30], limit=1, before_chapter=after_chapter + 1)
            refs.extend(hits)
        except Exception:
            continue
    # Dedup by chapter.
    seen = set()
    out = []
    for r in refs:
        ch = r.get("chapter")
        if ch in seen:
            continue
        seen.add(ch)
        out.append(r)
    return out[:8]


def _writer_call(
    *,
    chapter_outline: dict,
    style_refs: list[dict],
    is_revision: bool,
    previous_attempt: dict | None,
    chapter_index: int,
    cached_blocks: list,
) -> tuple[str, float, int]:
    user = build_writer_user_message(
        chapter_outline=chapter_outline,
        style_refs=style_refs,
        is_revision=is_revision,
        previous_attempt=previous_attempt,
        chapter_index=chapter_index,
    )
    resp = llm.call(
        agent="draft.writer",
        model=MODEL_STRONG,
        system=[{"type": "text", "text": WRITER_SYSTEM}, *cached_blocks],
        messages=[{"role": "user", "content": user}],
        max_tokens=8000,
        temperature=0.75,
    )
    return resp.text or "", resp.cost_usd, resp.elapsed_ms


def _reviewer_call(
    *,
    name: str,
    system_text: str,
    tool: dict,
    cached_blocks: list,
    chapter_outline: dict,
    prose: str,
    chapter_index: int,
) -> tuple[dict, float]:
    user = (
        f"# 第 {chapter_index} 章 · 待审\n\n"
        f"## 本章大纲\n{json.dumps(chapter_outline, ensure_ascii=False, indent=2)}\n\n"
        f"## 章节正文\n\n{prose}\n\n"
        "请按你的职责审查并调用工具返回结果。"
    )
    resp = llm.call(
        agent=f"draft.review.{name}",
        model=MODEL_FAST,
        system=[{"type": "text", "text": system_text}, *cached_blocks],
        messages=[{"role": "user", "content": user}],
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        max_tokens=4000,
        temperature=0.2,
    )
    out = (resp.tool_use or {}).get("input", {}) or {}
    if not out and resp.text:
        out = _coerce_dict(resp.text)
    # Defensive: ensure 'issues' is a list of dicts.
    issues = out.get("issues", [])
    if isinstance(issues, str):
        try:
            issues = json.loads(issues)
        except json.JSONDecodeError:
            issues = []
    out["issues"] = [it for it in (issues or []) if isinstance(it, dict)]
    return out, resp.cost_usd


def _editor_call(
    *,
    reviews: dict[str, dict],
    chapter_index: int,
    attempt: int,
    max_attempts: int,
) -> tuple[dict, float]:
    user = (
        f"# 第 {chapter_index} 章 · 第 {attempt}/{max_attempts} 轮审查\n\n"
        f"## 三位审查员的输出\n\n"
        f"### 文风审查\n{json.dumps(reviews.get('style', {}), ensure_ascii=False, indent=2)}\n\n"
        f"### 剧情审查\n{json.dumps(reviews.get('plot', {}), ensure_ascii=False, indent=2)}\n\n"
        f"### 一致性审查\n{json.dumps(reviews.get('consistency', {}), ensure_ascii=False, indent=2)}\n\n"
        "请合并去重、做决策、（如需要）写 revision_brief，调用 decide_revision。"
    )
    try:
        resp = llm.call(
            agent="draft.editor",
            model=MODEL_FAST,
            system=EDITOR_SYSTEM,
            messages=[{"role": "user", "content": user}],
            tools=[EDITOR_TOOL],
            tool_choice={"type": "tool", "name": EDITOR_TOOL["name"]},
            max_tokens=4000,
            temperature=0.2,
        )
    except Exception:
        return heuristic_decision(reviews, attempt, max_attempts), 0.0

    out = (resp.tool_use or {}).get("input", {}) or {}
    if not out and resp.text:
        out = _coerce_dict(resp.text)
    if "decision" not in out or out.get("decision") not in {"approve", "revise", "ship_with_warnings"}:
        # Editor didn't return valid output — fall back to heuristic.
        out = heuristic_decision(reviews, attempt, max_attempts)
    return out, resp.cost_usd


def write_chapter(
    *,
    outline_run_id: int,
    chapter_index: int,
    skip_reviews: bool = False,
    max_attempts: int = 3,
) -> dict[str, Any]:
    # 1) Load outline + chapter outline
    with session_scope() as s:
        run = s.get(OutlineRun, outline_run_id)
        if not run:
            raise ValueError(f"no OutlineRun id={outline_run_id}")
        chapters = list(run.chapters_json or [])
        chapter_outline = next(
            (c for c in chapters
             if isinstance(c, dict) and c.get("chapter_index") == chapter_index),
            None,
        )
        if not chapter_outline:
            raise ValueError(f"chapter {chapter_index} not in OutlineRun {outline_run_id}")
        # Determine the "after_chapter" for cached context — this is the
        # chapter PRIOR to the one we're writing.
        after_chapter = max(0, chapter_index - 1)

    # 2) Build cached context (entities/foreshadowings/mysteries/world rules etc.)
    ctx = _gather_context(after_chapter)
    cached_blocks = _ctx_blocks(ctx)

    # 3) Style references via FTS
    style_refs = _gather_style_refs(
        after_chapter=after_chapter,
        must_include=chapter_outline.get("must_include") or [],
    )

    # 4) Create or reuse a ChapterDraft row.
    with session_scope() as s:
        existing = s.execute(
            select(ChapterDraft).where(
                ChapterDraft.outline_run_id == outline_run_id,
                ChapterDraft.chapter_index == chapter_index,
            ).limit(1)
        ).scalar_one_or_none()
        if existing:
            draft_id = existing.id
            existing.status = "writing"
            existing.attempts_json = []
            existing.cost_usd = 0.0
            existing.final_text = None
            existing.updated_at = datetime.utcnow()
        else:
            row = ChapterDraft(
                outline_run_id=outline_run_id,
                chapter_index=chapter_index,
                title=chapter_outline.get("title"),
                status="writing",
            )
            s.add(row)
            s.flush()
            draft_id = row.id

    attempts: list[dict] = []
    prev_attempt_feedback: dict | None = None
    total_cost = 0.0
    final_text = ""
    final_status = "approved"

    def _flush_progress(stage: str) -> None:
        """Push current `attempts` + total_cost + a `stage` marker to the
        ChapterDraft row so a polling client can show fine-grained progress."""
        with session_scope() as s:
            d = s.get(ChapterDraft, draft_id)
            if d is None:
                return
            d.attempts_json = list(attempts)
            d.cost_usd = total_cost
            d.status = stage
            d.updated_at = datetime.utcnow()

    for attempt in range(1, max_attempts + 1):
        # Mark the attempt-in-progress so polling can show "Writer 写第 N 轮"
        attempt_record = {"attempt": attempt, "stage": "writer"}
        attempts.append(attempt_record)
        _flush_progress(f"attempt_{attempt}_writer")

        prose, w_cost, w_ms = _writer_call(
            chapter_outline=chapter_outline,
            style_refs=style_refs,
            is_revision=attempt > 1,
            previous_attempt=prev_attempt_feedback,
            chapter_index=chapter_index,
            cached_blocks=cached_blocks,
        )
        total_cost += w_cost
        attempt_record.update({
            "prose": prose,
            "writer_cost_usd": w_cost,
            "writer_elapsed_ms": w_ms,
            "stage": "writer_done",
        })
        _flush_progress(f"attempt_{attempt}_writer_done")

        if skip_reviews:
            attempt_record["reviews"] = None
            attempt_record["editor"] = {
                "decision": "approve",
                "rationale": "skip_reviews=true",
                "merged_issues": [],
            }
            attempt_record["stage"] = "done"
            final_text = prose
            final_status = "approved"
            break

        # Run 3 reviewers in parallel — IO bound, threadpool fits.
        attempt_record["stage"] = "reviewing"
        attempt_record["reviews"] = {}
        _flush_progress(f"attempt_{attempt}_reviewing")
        reviews: dict[str, dict] = {}
        review_jobs = [
            ("style", STYLE_REVIEWER_SYSTEM, STYLE_REVIEWER_TOOL),
            ("plot", PLOT_REVIEWER_SYSTEM, PLOT_REVIEWER_TOOL),
            ("consistency", CONSISTENCY_REVIEWER_SYSTEM, CONSISTENCY_REVIEWER_TOOL),
        ]
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = {
                ex.submit(
                    _reviewer_call,
                    name=name,
                    system_text=sys_text,
                    tool=tool,
                    cached_blocks=cached_blocks,
                    chapter_outline=chapter_outline,
                    prose=prose,
                    chapter_index=chapter_index,
                ): name
                for name, sys_text, tool in review_jobs
            }
            # As reviewers finish, update the row so UI shows lanes ticking off.
            for fut in futs:
                name = futs[fut]
                try:
                    out, c = fut.result()
                except Exception as exc:
                    out = {"issues": [], "overall": f"reviewer error: {exc}"}
                    c = 0.0
                reviews[name] = out
                total_cost += c
                attempt_record["reviews"] = dict(reviews)  # snapshot for poller
                _flush_progress(f"attempt_{attempt}_reviewing")

        attempt_record["reviews"] = reviews

        # Editor adjudicates
        attempt_record["stage"] = "editor"
        _flush_progress(f"attempt_{attempt}_editor")
        editor_out, e_cost = _editor_call(
            reviews=reviews,
            chapter_index=chapter_index,
            attempt=attempt,
            max_attempts=max_attempts,
        )
        total_cost += e_cost
        attempt_record["editor"] = editor_out
        attempt_record["stage"] = "done"
        _flush_progress(f"attempt_{attempt}_done")

        decision = editor_out.get("decision")
        if decision in {"approve", "ship_with_warnings"}:
            final_text = prose
            final_status = decision
            break

        # Set up next iteration's revision feedback
        merged = editor_out.get("merged_issues") or []
        failed = [i for i in merged if i.get("severity") in {"blocker", "major"}]
        prev_attempt_feedback = {
            "prose": prose,
            "revision_brief": editor_out.get("revision_brief", ""),
            "failed_issues_quoted": failed,
        }
    else:
        # Fell through all attempts without break
        final_text = (attempts[-1]["prose"] if attempts else "")
        final_status = "shipped_with_warnings"

    # Persist
    with session_scope() as s:
        d = s.get(ChapterDraft, draft_id)
        d.attempts_json = attempts
        d.final_text = final_text
        d.cost_usd = total_cost
        d.status = final_status
        d.updated_at = datetime.utcnow()

    return {
        "id": draft_id,
        "chapter_index": chapter_index,
        "status": final_status,
        "attempts": attempts,
        "final_text": final_text,
        "cost_usd": round(total_cost, 5),
    }


# ---------------------------------------------------------------------------
# Read APIs
# ---------------------------------------------------------------------------

def list_drafts(limit: int = 50) -> list[dict]:
    with session_scope() as s:
        rows = s.execute(
            select(ChapterDraft).order_by(desc(ChapterDraft.id)).limit(limit)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "outline_run_id": r.outline_run_id,
                "chapter_index": r.chapter_index,
                "title": r.title,
                "status": r.status,
                "n_attempts": len(r.attempts_json or []),
                "cost_usd": r.cost_usd,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]


def get_draft(draft_id: int) -> dict | None:
    with session_scope() as s:
        r = s.get(ChapterDraft, draft_id)
        if not r:
            return None
        return {
            "id": r.id,
            "outline_run_id": r.outline_run_id,
            "chapter_index": r.chapter_index,
            "title": r.title,
            "status": r.status,
            "attempts": r.attempts_json or [],
            "final_text": r.final_text,
            "cost_usd": r.cost_usd,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }


def update_final_text(draft_id: int, text: str) -> bool:
    with session_scope() as s:
        r = s.get(ChapterDraft, draft_id)
        if not r:
            return False
        r.final_text = text
        r.status = "approved"
        r.updated_at = datetime.utcnow()
    return True
