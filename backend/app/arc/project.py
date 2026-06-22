"""Whole-book story projection.

Strategy (the 整本故事弧推演 backbone):
  1. The chosen story ARC is the top-down skeleton — it already plans the key
     questions (core_truths), per-phase foreshadow payoff, climax, ending, and
     total size. That bounds the projection (no infinite recursion, no fragile
     "should I stop?" per step — the arc's phases decide the endpoint).
  2. _sanitize_phases repairs the arc's phase ranges. Single-shot arc generation
     degrades at the tail (end<start, gaps, overlaps), so we re-anchor every
     phase to a clean, contiguous, monotonic range starting at after_chapter+1.
  3. We expand EACH phase into chapter outlines (outline.refine, with range
     overrides + previous-phase-tail continuity), aggregate, and renumber the
     chapters contiguously — so drift never compounds across phases.
  4. A completeness 裁决 checks the full projection: are all core_truths revealed
     and the major foreshadowings resolved? Gaps are surfaced, not hidden.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..llm import client as llm
from ..outline import pipeline as outline


_PER_PHASE_MIN, _PER_PHASE_MAX = 4, 24


def _as_str(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        for k in ("text", "event", "content", "desc", "name", "value"):
            if isinstance(v.get(k), str):
                return v[k]
        return "；".join(str(x) for x in v.values() if isinstance(x, (str, int, float)))
    return str(v) if v is not None else ""


def _str_list(v) -> list[str]:
    items = v if isinstance(v, list) else ([v] if v is not None else [])
    out = [_as_str(x).strip() for x in items]
    return [x for x in out if x]


def _clean_title(t) -> str:
    """Strip a stale leading chapter-number prefix the model bakes into titles
    (e.g. '第169章前夜余烬' → '前夜余烬'), so it matches the re-anchored index."""
    s = _as_str(t).strip()
    s = re.sub(r"^第?\s*\d+\s*章[\s:：·、.\-]*", "", s).strip()
    return s or _as_str(t).strip()


def _coerce_list(v: Any) -> list:
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            d = json.loads(v)
            return d if isinstance(d, list) else []
        except Exception:
            return []
    return []


def _phase_span(p: dict, fallback: int) -> int:
    """Intended chapter count for a phase; repairs garbled (end<start) ranges."""
    s, e = p.get("chapter_start"), p.get("chapter_end")
    if isinstance(s, int) and isinstance(e, int) and e >= s:
        return max(_PER_PHASE_MIN, min(e - s + 1, _PER_PHASE_MAX))
    return fallback


def _sanitize_phases(phases: list[dict], after_chapter: int, total_est: int | None) -> list[dict]:
    """Re-anchor phases to clean contiguous ranges from after_chapter+1.

    Preserves each phase's narrative content + intended span, but fixes absolute
    numbering so the arc's garbled-tail ranges never reach the outline model.
    """
    valid = [p for p in phases if isinstance(p, dict)]
    n = len(valid) or 1
    # fallback per-phase length from the size estimate
    fallback = _PER_PHASE_MIN
    if isinstance(total_est, int) and total_est > 0:
        fallback = max(_PER_PHASE_MIN, min(round(total_est / n), _PER_PHASE_MAX))

    out: list[dict] = []
    cursor = after_chapter + 1
    for i, p in enumerate(valid):
        span = _phase_span(p, fallback)
        start, end = cursor, cursor + span - 1
        out.append({
            "phase_index": i,
            "name": p.get("name") or f"阶段 {i + 1}",
            "start": start,
            "end": end,
            "summary": p.get("summary") or "",
            "orig_start": p.get("chapter_start"),
            "orig_end": p.get("chapter_end"),
        })
        cursor = end + 1
    return out


# --------------------------------------------------------------------------
# Completeness 裁决 — JSON-in-text on doubao-code (large structured context).
# --------------------------------------------------------------------------

_VERDICT_SYSTEM = """你是长篇小说的结构审稿人。给你：(1) 一部小说后续故事弧的【关键问题 core_truths】与【未收束伏笔】；(2) 推演出的【逐章大纲】。
判断这份整本推演是否把关键问题都揭晓、把主要伏笔都收束、节奏是否连贯无断层。

# 输出格式（严格）
只输出一个 JSON 对象，不要任何其它文字、不要 markdown 围栏：
{"revealed_truths": ["已在大纲中揭晓的关键问题"],
 "unresolved_truths": ["大纲里没有交代的关键问题"],
 "resolved_foreshadow_ids": [已收束的伏笔id整数],
 "still_open_foreshadow_ids": [仍未收束的伏笔id整数],
 "coherence_issues": ["节奏/断层/逻辑问题，没有则空数组"],
 "coverage_note": "一句话总评覆盖度",
 "verdict": "pass 或 needs_work"}"""


def _loads(s: str) -> dict:
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


def _judge_completeness(arc: dict, chapters: list[dict]) -> tuple[dict, float]:
    core_truths = arc.get("core_truths") or []
    unresolved = arc.get("unresolved_foreshadow_ids") or []
    truths_brief = [{"q": (t.get("question") if isinstance(t, dict) else str(t)),
                     "fs": (t.get("related_foreshadow_ids") if isinstance(t, dict) else None)}
                    for t in core_truths]
    outline_brief = [{"ch": c.get("chapter_index"), "title": c.get("title"),
                      "must": (c.get("must_include") or [])[:3]} for c in chapters]
    user = (
        "【关键问题 core_truths】\n" + json.dumps(truths_brief, ensure_ascii=False)
        + "\n\n【arc 标注的未收束伏笔 id】\n" + json.dumps(unresolved, ensure_ascii=False)
        + "\n\n【推演逐章大纲】\n" + json.dumps(outline_brief, ensure_ascii=False)
    )
    resp = llm.call(
        agent="arc.project.judge", model="doubao-seed-2.0-code",
        system=_VERDICT_SYSTEM, messages=[{"role": "user", "content": user}],
        max_tokens=4000, temperature=0.2,
    )
    return _loads(resp.text or ""), resp.cost_usd


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------

def _load_arc(arc_run_id: int, chosen_index: int) -> tuple[dict, int]:
    from ..db import session_scope
    from ..memory.models import ArcRun
    with session_scope() as s:
        run = s.get(ArcRun, arc_run_id)
        if not run:
            raise ValueError(f"no ArcRun id={arc_run_id}")
        cands = _coerce_list(run.candidates_json)
        ci = chosen_index if 0 <= chosen_index < len(cands) else (run.chosen_index or 0)
        arc = cands[ci] if 0 <= ci < len(cands) and isinstance(cands[ci], dict) else {}
        return arc, run.after_chapter


def project_full_book(arc_run_id: int, chosen_index: int, on_stage=None) -> dict[str, Any]:
    def _stage(st):
        if on_stage:
            try:
                on_stage(st)
            except Exception:
                pass

    arc, after_chapter = _load_arc(arc_run_id, chosen_index)
    phases = _coerce_list(arc.get("phases"))
    if not phases:
        raise ValueError("chosen arc has no phases to project")
    total_est = arc.get("total_chapters_estimated")
    sane = _sanitize_phases(phases, after_chapter, total_est if isinstance(total_est, int) else None)

    all_chapters: list[dict] = []
    outline_run_ids: list[int] = []
    cost = 0.0
    cursor = after_chapter + 1
    prev_tail: str | None = None

    for sp in sane:
        i = sp["phase_index"]
        _stage(f"展开阶段 {i + 1}/{len(sane)}：{sp['name']}")
        try:
            res = outline.refine(
                source_kind="arc", source_run_id=arc_run_id, chosen_index=chosen_index,
                phase_index=i, chapter_start_override=sp["start"], chapter_end_override=sp["end"],
                continuity_hint=prev_tail, persist=False,
            )
        except Exception as e:  # noqa: BLE001 — one bad phase shouldn't kill the whole projection
            res = {"chapters": [], "cost_usd": 0.0, "_error": str(e)[:200]}
        chs = [c for c in (res.get("chapters") or []) if isinstance(c, dict)]
        # re-anchor numbering contiguously (kills tail drift) + clean fields:
        # the model bakes the ORIGINAL chapter number into the title (e.g.
        # "第169章…") and sometimes returns must_include as dicts — strip the
        # stale prefix so it matches the re-anchored index, and coerce to strings.
        for c in chs:
            c["chapter_index"] = cursor
            c["phase_index"] = i
            c["phase_name"] = sp["name"]
            c["title"] = _clean_title(c.get("title"))
            c["must_include"] = _str_list(c.get("must_include"))
            if c.get("ending_hook") is not None:
                c["ending_hook"] = _as_str(c.get("ending_hook"))
            cursor += 1
        # Persist this phase as a real, draftable OutlineRun (single source of
        # truth — /outline edits it, /draft writes from it). The projection layer
        # only aggregates + judges on top; it does not keep a separate outline copy.
        if chs:
            rid = _persist_phase_outline(arc_run_id, chosen_index, i, sp["name"], chs,
                                         res.get("cost_usd", 0.0))
            if rid:
                outline_run_ids.append(rid)
        all_chapters.extend(chs)
        cost += res.get("cost_usd", 0.0)
        if chs:
            last = chs[-1]
            prev_tail = (f"第 {last['chapter_index']} 章《{last.get('title')}》："
                         + "；".join((last.get("must_include") or [])[:4]))[:300]

    _stage("完整性裁决")
    verdict: dict = {}
    try:
        verdict, vcost = _judge_completeness(arc, all_chapters)
        cost += vcost
    except Exception as e:  # noqa: BLE001
        verdict = {"verdict": "unknown", "coverage_note": f"裁决失败：{str(e)[:120]}"}

    end_chapter = (all_chapters[-1]["chapter_index"] if all_chapters else after_chapter)
    return {
        "arc_title": arc.get("title"),
        "after_chapter": after_chapter,
        "end_chapter": end_chapter,
        "total_chapters": len(all_chapters),
        "phases": sane,
        "chapters": all_chapters,
        "outline_run_ids": outline_run_ids,
        "verdict": verdict,
        "cost_usd": round(cost, 5),
    }


def _persist_phase_outline(arc_run_id: int, chosen_index: int, phase_index: int,
                           phase_name: str, chapters: list[dict], cost: float) -> int | None:
    """Write one phase's re-anchored chapters as a real OutlineRun so /outline can
    edit it and /draft can write from it. Returns the new OutlineRun id."""
    from datetime import datetime
    from ..db import session_scope
    from ..memory.models import OutlineRun
    try:
        with session_scope() as s:
            row = OutlineRun(
                source_kind="arc", source_run_id=arc_run_id, source_chosen_index=chosen_index,
                phase_index=phase_index, phase_name=phase_name,
                chapter_start=chapters[0]["chapter_index"],
                chapter_end=chapters[-1]["chapter_index"],
                chapters_json=chapters, user_hints="（整本推演自动生成）",
                cost_usd=cost, created_at=datetime.utcnow(),
            )
            s.add(row); s.flush()
            return row.id
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# Job persistence (background + poll), mirrors bilingual/revoice.
# --------------------------------------------------------------------------

def create_job(arc_run_id: int, chosen_index: int) -> int:
    from datetime import datetime
    from ..db import session_scope
    from ..memory.models import StoryProjection
    with session_scope() as s:
        row = StoryProjection(arc_run_id=arc_run_id, chosen_index=chosen_index,
                              status="projecting", updated_at=datetime.utcnow())
        s.add(row); s.flush()
        return row.id


def _set_stage(job_id: int, stage: str) -> None:
    from datetime import datetime
    from ..db import session_scope
    from ..memory.models import StoryProjection
    try:
        with session_scope() as s:
            row = s.get(StoryProjection, job_id)
            if row:
                row.stage = stage; row.updated_at = datetime.utcnow()
    except Exception:
        pass


def run_and_store(job_id: int, arc_run_id: int, chosen_index: int) -> None:
    from datetime import datetime
    from ..db import session_scope
    from ..memory.models import StoryProjection
    try:
        res = project_full_book(arc_run_id, chosen_index, on_stage=lambda st: _set_stage(job_id, st))
        with session_scope() as s:
            row = s.get(StoryProjection, job_id)
            if row:
                row.after_chapter = res["after_chapter"]
                row.end_chapter = res["end_chapter"]
                row.total_chapters = res["total_chapters"]
                row.arc_title = res["arc_title"]
                row.phases_json = res["phases"]
                row.chapters_json = res["chapters"]
                row.outline_run_ids = res.get("outline_run_ids") or []
                row.verdict_json = res["verdict"]
                row.cost_usd = res["cost_usd"]
                row.status = "done"; row.stage = "done"
                row.updated_at = datetime.utcnow()
    except Exception as e:  # noqa: BLE001
        with session_scope() as s:
            row = s.get(StoryProjection, job_id)
            if row:
                row.status = "failed"; row.error = str(e)[:500]
                row.updated_at = datetime.utcnow()


def list_jobs(limit: int = 20) -> list[dict]:
    from sqlalchemy import select, desc
    from ..db import session_scope
    from ..memory.models import StoryProjection
    with session_scope() as s:
        rows = s.execute(select(StoryProjection).order_by(desc(StoryProjection.id)).limit(limit)).scalars().all()
        return [{"id": r.id, "arc_run_id": r.arc_run_id, "arc_title": r.arc_title,
                 "status": r.status, "stage": r.stage, "after_chapter": r.after_chapter,
                 "end_chapter": r.end_chapter, "total_chapters": r.total_chapters,
                 "cost_usd": r.cost_usd,
                 "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


def get_job(job_id: int) -> dict | None:
    from ..db import session_scope
    from ..memory.models import StoryProjection
    with session_scope() as s:
        r = s.get(StoryProjection, job_id)
        if not r:
            return None
        return {"id": r.id, "arc_run_id": r.arc_run_id, "chosen_index": r.chosen_index,
                "arc_title": r.arc_title, "status": r.status, "stage": r.stage or "",
                "after_chapter": r.after_chapter, "end_chapter": r.end_chapter,
                "total_chapters": r.total_chapters, "phases": r.phases_json or [],
                "chapters": r.chapters_json or [], "outline_run_ids": r.outline_run_ids or [],
                "verdict": r.verdict_json or {},
                "error": r.error, "cost_usd": r.cost_usd,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None}
