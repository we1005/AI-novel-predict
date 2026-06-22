"""Three-stage plot prediction pipeline.

A) diverge — strong model, T=0.95, N candidates with foreshadow id refs.
B) constrain — strong model, T=0.2, score 4 dims, pick winner.
C) write — strong model, T=0.75, expand winner into 1–3 chapters of prose, streamed.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select

from ..config import DEFAULT_CANDIDATES, MODEL_STRONG
from ..db import session_scope
from ..llm import client as llm
from ..llm.prompts.prediction import (
    CANDIDATE_SYSTEM,
    CANDIDATE_JSON_HINT,
    CANDIDATE_TOOL,
    SCORING_SYSTEM,
    SCORING_JSON_HINT,
    SCORING_TOOL,
    WRITING_SYSTEM_TEMPLATE,
)
from ..memory import fts as fts_recall
from ..memory.models import (
    Chapter,
    Entity,
    EntityState,
    Foreshadowing,
    Mystery,
    PlotPoint,
    PredictionRun,
    WorldRule,
)


def _gather_context(after_chapter: int) -> dict[str, Any]:
    """Collect everything the prediction needs and shape into stable JSON blobs."""

    with session_scope() as s:
        open_fs = s.execute(
            select(Foreshadowing).where(
                Foreshadowing.status == "open",
                Foreshadowing.planted_chapter <= after_chapter,
            )
        ).scalars().all()
        rules = s.execute(select(WorldRule)).scalars().all()
        recent_plot = s.execute(
            select(PlotPoint)
            .where(PlotPoint.chapter <= after_chapter)
            .order_by(desc(PlotPoint.chapter))
            .limit(15)
        ).scalars().all()
        recent_chapters = s.execute(
            select(Chapter)
            .where(Chapter.number <= after_chapter)
            .order_by(desc(Chapter.number))
            .limit(5)
        ).scalars().all()
        # Latest state of every "important" person.
        # Live macro mysteries — the "reader still asking" questions that
        # continuation should preserve as ongoing tension.
        live_mysteries = s.execute(
            select(Mystery).where(
                Mystery.status.in_(["open", "sharpened", "partially_resolved"]),
                Mystery.confidence >= 50,
            )
        ).scalars().all()

        people = s.execute(
            select(Entity).where(Entity.type == "person", Entity.importance >= 5)
        ).scalars().all()
        people_states: list[dict] = []
        for p in people:
            row = s.execute(
                select(EntityState)
                .where(EntityState.entity_id == p.id, EntityState.chapter <= after_chapter)
                .order_by(desc(EntityState.chapter))
                .limit(1)
            ).scalar_one_or_none()
            people_states.append(
                {
                    "name": p.name,
                    "importance": p.importance,
                    "state_at": row.chapter if row else None,
                    "state": row.state_json if row else {},
                    "description": (p.description or "")[:120],
                }
            )

        return {
            "open_foreshadowings": [
                {
                    "id": f.id,
                    "type": f.type,
                    "planted_chapter": f.planted_chapter,
                    "description": f.description,
                }
                for f in open_fs
            ],
            "world_rules": [{"term": r.term, "definition": r.definition} for r in rules],
            "recent_plot": [
                {"chapter": pp.chapter, "summary": pp.summary, "importance": pp.importance}
                for pp in reversed(recent_plot)
            ],
            "recent_chapter_titles": [
                {"chapter": c.number, "title": c.title}
                for c in reversed(recent_chapters)
            ],
            "characters": sorted(people_states, key=lambda x: -x["importance"]),
            "open_mysteries": sorted(
                [
                    {
                        "id": m.id,
                        "category": m.category,
                        "severity": m.severity,
                        "status": m.status,
                        "confidence": m.confidence,
                        "question": m.question,
                        "why_it_matters": (m.why_it_matters or "")[:200],
                    }
                    for m in live_mysteries
                ],
                key=lambda x: (
                    {"core": 0, "major": 1, "minor": 2}.get(x["severity"] or "major", 9),
                    -(x["confidence"] or 0),
                ),
            ),
        }


def _style_block() -> dict[str, Any] | None:
    """If the active book has a style profile, surface its narrative structure +
    tropes + setting so prediction (predict & arc) follows the BOOK's actual
    storytelling habits instead of a generic 网文-macro-mystery template. When
    mimic is on, this is binding; otherwise it's reference."""
    try:
        from ..style.pipeline import get_profile
        p = get_profile()
    except Exception:
        p = None
    if not p:
        return None
    prof = p.get("profile") or {}
    ns = prof.get("narrative_structure") or {}
    parts = []
    if ns:
        parts.append(
            "叙事结构：mode=%s；技法=%s；视角=%s；节奏=%s"
            % (ns.get("mode"), "、".join(ns.get("techniques") or []),
               (ns.get("pov_structure") or "")[:120], (ns.get("pacing") or "")[:160])
        )
    tropes = prof.get("tropes")
    if isinstance(tropes, list) and tropes:
        parts.append("作者常用套路/母题：" + "、".join(str(t) for t in tropes[:10]))
    if prof.get("setting_register"):
        parts.append("世界观/文化语域：" + str(prof["setting_register"])[:200])
    if not parts:
        return None
    if p.get("mimic_enabled"):
        head = "【本书叙事基因 — 已开启「模仿原作者」，预测后续剧情必须顺着作者的叙事结构、节奏与套路走】\n"
    else:
        head = "【本书叙事基因 — 预测时作为参考，避免生成与本书气质相悖的走向】\n"
    return llm.cached_block(head + "\n".join("- " + x for x in parts))


def _ctx_blocks(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = [
        llm.cached_block("【未收束伏笔表】\n" + llm.stable_json(ctx["open_foreshadowings"])),
        llm.cached_block(
            "【读者追问的核心问题（宏观疑点 — 续写时这些悬念不能丢）】\n"
            + llm.stable_json(ctx.get("open_mysteries", []))
        ),
        llm.cached_block("【世界规则】\n" + llm.stable_json(ctx["world_rules"])),
        llm.cached_block("【主要人物当前状态】\n" + llm.stable_json(ctx["characters"])),
        llm.cached_block("【近期重要剧情节点】\n" + llm.stable_json(ctx["recent_plot"])),
        llm.cached_block("【最近 5 章标题】\n" + llm.stable_json(ctx["recent_chapter_titles"])),
    ]
    sb = _style_block()
    if sb:
        blocks.append(sb)
    return blocks


def _loads_json(s: str) -> dict:
    """Parse a JSON object out of model text (strips fences, repairs)."""
    import json
    import re
    s = re.sub(r"```json|```", "", s or "").strip()
    try:
        d = json.loads(s)
    except Exception:
        try:
            from json_repair import repair_json
            d = json.loads(repair_json(s))
        except Exception:
            return {}
    return d if isinstance(d, dict) else {}


# Stage A
def stage_a(after_chapter: int, n: int = DEFAULT_CANDIDATES) -> tuple[list[dict], dict, float]:
    ctx = _gather_context(after_chapter)
    blocks = _ctx_blocks(ctx)
    user = (
        f"已写到第 {after_chapter} 章。请提出 {n} 条**走向迥异**的下一段（约 1~3 章规模）剧情候选。\n"
        "记得在 uses_foreshadow_ids 中标注实际利用的伏笔 id。"
    )
    # JSON-in-text rather than forced tool_choice: doubao/volc reasoning models
    # silently emit finish_reason=tool_calls with an EMPTY tool_calls array when
    # the context is large (predict context is ~90k chars), yielding 0 candidates.
    # Plain-JSON output + repair-parse is reliable at that size (改进记录 #15).
    resp = llm.call(
        agent="predict.diverge",
        model=MODEL_STRONG,
        system=[{"type": "text", "text": CANDIDATE_SYSTEM + CANDIDATE_JSON_HINT}, *blocks],
        messages=[{"role": "user", "content": user}],
        max_tokens=8000,
        temperature=0.95,
        top_p=0.95,
    )
    cands = _loads_json(resp.text).get("candidates", []) or []
    return cands, ctx, resp.cost_usd


# Stage B
def stage_b(candidates: list[dict], ctx: dict) -> tuple[dict, float]:
    blocks = _ctx_blocks(ctx)
    user = (
        "以下是 N 条候选剧情。请按职责打分并选出 winner。\n\n候选：\n"
        + llm.stable_json(candidates)
    )
    resp = llm.call(
        agent="predict.score",
        model=MODEL_STRONG,
        system=[{"type": "text", "text": SCORING_SYSTEM + SCORING_JSON_HINT}, *blocks],
        messages=[{"role": "user", "content": user}],
        max_tokens=6000,
        temperature=0.2,
    )
    return _loads_json(resp.text), resp.cost_usd


# Stage C — streaming
def stage_c_stream(
    chosen: dict,
    ctx: dict,
    *,
    after_chapter: int,
    style_chunks: int = 4,
) -> Generator[str, None, dict]:
    """Yield text chunks; final yielded value is unused — caller must check
    ``stage_c_collect`` for usage/cost via the audit table."""

    # Pull style-reference snippets via FTS using the synopsis as query.
    query = chosen.get("synopsis", "")[:120] or chosen.get("title", "")
    style_hits = fts_recall.search(query, limit=style_chunks, before_chapter=after_chapter + 1)
    style_blob = "\n\n---\n\n".join(
        f"[{h['chapter']}章 {h.get('title', '')}] {h.get('snip', '')}" for h in style_hits
    )

    blocks = [
        *_ctx_blocks(ctx),
        llm.cached_block("【风格参考片段（来自原文检索）】\n" + style_blob),
    ]
    user = (
        "请按以下选定的剧情走向写出 1~3 个新章节，严格遵守风格守则与情节守则：\n\n"
        + llm.stable_json(chosen)
    )

    accumulated: list[str] = []
    for chunk in llm.stream_text(
        agent="predict.write",
        model=MODEL_STRONG,
        system=[{"type": "text", "text": WRITING_SYSTEM_TEMPLATE}, *blocks],
        messages=[{"role": "user", "content": user}],
        max_tokens=8000,
        temperature=0.75,
    ):
        accumulated.append(chunk)
        yield chunk
    return {"text": "".join(accumulated)}


def _ensure_winner(score: dict, n_cands: int) -> dict:
    """Guarantee a valid winner_index. The scoring model occasionally omits it
    or returns null/out-of-range; without this, outline.refine crashes with
    'chosen_index out of range'. Fall back to the highest summed-score candidate."""
    if not isinstance(score, dict):
        score = {}
    wi = score.get("winner_index")
    if isinstance(wi, int) and 0 <= wi < n_cands:
        return score
    best, best_sum = 0, -1.0
    for sc in (score.get("scores") or []):
        idx = sc.get("index")
        if not isinstance(idx, int) or not (0 <= idx < n_cands):
            continue
        ssum = sum(float(sc.get(k, 0) or 0) for k in
                   ("coherence", "foreshadow_use", "character_consistency", "novelty"))
        if ssum > best_sum:
            best_sum, best = ssum, idx
    score["winner_index"] = best if n_cands else 0
    if not score.get("winner_reason"):
        score["winner_reason"] = "（自动选择综合得分最高的候选）"
    return score


def run_predict(after_chapter: int, n: int = DEFAULT_CANDIDATES) -> dict:
    """A + B (no write). Returns saved PredictionRun id."""

    cands, ctx, cost_a = stage_a(after_chapter, n=n)
    score, cost_b = stage_b(cands, ctx)
    score = _ensure_winner(score, len(cands))
    with session_scope() as s:
        run = PredictionRun(
            after_chapter=after_chapter,
            candidates_json=cands,
            scores_json=score,
            cost_usd=cost_a + cost_b,
            created_at=datetime.utcnow(),
        )
        s.add(run)
        s.flush()
        return {
            "id": run.id,
            "candidates": cands,
            "scores": score,
            "cost_usd": cost_a + cost_b,
        }
