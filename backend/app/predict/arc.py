"""Whole-story arc prediction pipeline (2 stages).

Reuses ``_gather_context`` and ``_ctx_blocks`` from the chapter-level
``pipeline`` module — the cached context is the same; only the prompts and
output schema differ.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def _coerce_list(v: Any) -> list:
    """Decode arc/score arrays from whatever shape qwen returns this time.

    Qwen3.5-flash has two failure modes worth handling:
      1. Stringifying the array (returning JSON-encoded string instead of array).
      2. Producing the JSON itself with structural errors (extra ``}``, trailing
         comma, missing comma, etc.). Strict ``json.loads`` fails; ``json_repair``
         heals most of these.
    """

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


def _schema_json_hint(schema: dict) -> str:
    """Build a strict 'output only JSON matching this schema' instruction.

    JSON-in-text instead of forced tool_choice: doubao/volc reasoning models
    silently return finish_reason=tool_calls with an EMPTY tool_calls array (and
    empty content) on large context (arc context is ~90k chars), producing 0
    arcs/scores. Embedding the real schema keeps the shape accurate (改进记录 #15).
    """
    return ("\n\n# 输出格式（严格 · 覆盖前述任何「调用工具」指示）\n"
            "只输出一个 JSON 对象，不要任何其它文字、不要 markdown 代码块围栏。"
            "必须严格符合以下 JSON Schema：\n" + json.dumps(schema, ensure_ascii=False))


def _extract_json_from_text(text: str, key: str) -> Any:
    """Fallback when the model writes JSON to message content instead of
    invoking the tool. Uses ``json-repair`` to tolerate model errors."""

    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s.rsplit("```", 1)[0]
        s = s.strip()
    try:
        from json_repair import repair_json

        obj = json.loads(repair_json(s))
    except Exception:
        return None
    if isinstance(obj, dict) and key in obj:
        return obj[key]
    if isinstance(obj, list):
        return obj
    return None

from sqlalchemy import desc, select

from ..config import MODEL_STRONG
from ..db import session_scope
from ..llm import client as llm
from ..llm.prompts.arc import (
    ARC_SCORING_SYSTEM,
    ARC_SCORING_TOOL,
    ARC_SYSTEM,
    ARC_TOOL,
)
from ..memory.models import ArcRun
from .pipeline import _ctx_blocks, _gather_context


def stage_a(after_chapter: int, n_candidates: int, target_chapters: int,
            user_hints: str = "") -> tuple[list[dict], dict, float]:
    ctx = _gather_context(after_chapter)
    blocks = _ctx_blocks(ctx)
    # User hints go AFTER cached blocks (so they invalidate the cache prefix
    # for THIS run only, then the rest stays cached). They're meant to be
    # high-prominence "directorial notes" so they sit immediately before the
    # user turn — recency dominates instruction-following.
    system_chain: list[Any] = [{"type": "text", "text": ARC_SYSTEM}, *blocks]
    if user_hints.strip():
        system_chain.append({
            "type": "text",
            "text": (
                "【用户创作偏好（导演备注 — 高优先级）】\n"
                + user_hints.strip()
                + "\n\n请让所有候选都明确反映上述偏好；偏好与硬约束冲突时硬约束优先。"
            ),
        })
    open_count = len(ctx["open_foreshadowings"])
    user = (
        f"已写到第 {after_chapter} 章。请提出 {n_candidates} 个**风格迥异、方向各不相同**的"
        f"完整故事弧候选，每个预计延展约 {target_chapters} 章。\n"
        f"当前有 {open_count} 条 open 伏笔——请尽量在阶段中覆盖至少 70%。\n"
        "记得用 foreshadow_ids_addressed 在每个阶段标注收束的伏笔 id。"
    )
    if user_hints.strip():
        user += "\n\n再次强调：每个候选都必须显式体现 system 中【用户创作偏好】里的方向。"
    system_chain[0] = {"type": "text", "text": ARC_SYSTEM + _schema_json_hint(ARC_TOOL["input_schema"])}
    resp = llm.call(
        agent="arc.diverge",
        model=MODEL_STRONG,
        system=system_chain,
        messages=[{"role": "user", "content": user}],
        max_tokens=16000,
        temperature=0.95,
        top_p=0.95,
    )
    arcs = _coerce_list((resp.tool_use or {}).get("input", {}).get("arcs", []))
    if not arcs and resp.text:
        # Model emitted JSON in content rather than via tool_use.
        parsed = _extract_json_from_text(resp.text, "arcs")
        if isinstance(parsed, list):
            arcs = parsed
    if not arcs:
        # Last-ditch debug: dump what we got so the user can see why.
        import logging

        log = logging.getLogger("arc")
        log.warning(
            "arc.diverge produced no arcs. tool_use=%s text(first 600)=%s",
            (resp.tool_use or {}).get("input", {}) if resp.tool_use else None,
            (resp.text or "")[:600],
        )
    # Some models also stringify nested phases.
    for a in arcs:
        if isinstance(a, dict):
            a["phases"] = _coerce_list(a.get("phases", []))
    return arcs, ctx, resp.cost_usd


def stage_b(arcs: list[dict], ctx: dict, user_hints: str = "") -> tuple[dict, float]:
    blocks = _ctx_blocks(ctx)
    system_chain: list[Any] = [{"type": "text", "text": ARC_SCORING_SYSTEM}, *blocks]
    if user_hints.strip():
        system_chain.append({
            "type": "text",
            "text": (
                "【用户创作偏好（评分时的关键参考）】\n"
                + user_hints.strip()
                + "\n\n打分时务必考量每个候选是否真正体现了上述偏好。novelty 与 coherence 的评分都应纳入这一点。"
            ),
        })
    user = (
        "以下是 N 个完整故事弧候选。请按职责打 5 维分并选出 winner。\n\n候选：\n"
        + llm.stable_json(arcs)
    )
    system_chain[0] = {"type": "text", "text": ARC_SCORING_SYSTEM + _schema_json_hint(ARC_SCORING_TOOL["input_schema"])}
    resp = llm.call(
        agent="arc.score",
        model=MODEL_STRONG,
        system=system_chain,
        messages=[{"role": "user", "content": user}],
        max_tokens=8000,
        temperature=0.2,
    )
    out = (resp.tool_use or {}).get("input", {}) or {}
    if not out and resp.text:
        parsed = _extract_json_from_text(resp.text, "scores")
        if isinstance(parsed, list):
            out = {"scores": parsed}
        elif isinstance(parsed, dict):
            out = parsed
    out["scores"] = _coerce_list(out.get("scores", []))
    out = _ensure_arc_winner(out, len(arcs))
    return out, resp.cost_usd


def _ensure_arc_winner(score: dict, n_arcs: int) -> dict:
    """Guarantee a valid winner_index. The JSON-in-text scorer sometimes omits
    it or returns null/out-of-range; without this, ArcRun.chosen_index is None
    and downstream outline.refine crashes with 'chosen_index out of range'.
    Falls back to the highest summed-score candidate."""
    if not isinstance(score, dict):
        score = {}
    wi = score.get("winner_index")
    if isinstance(wi, int) and 0 <= wi < n_arcs:
        return score
    best, best_sum = 0, -1.0
    dims = ("coherence", "foreshadow_use", "character_consistency", "novelty",
            "macro_logic", "pacing", "payoff", "originality")
    for sc in (score.get("scores") or []):
        if not isinstance(sc, dict):
            continue
        idx = sc.get("index")
        if not isinstance(idx, int) or not (0 <= idx < n_arcs):
            continue
        ssum = sum(float(sc.get(k, 0) or 0) for k in dims)
        if ssum > best_sum:
            best_sum, best = ssum, idx
    score["winner_index"] = best if n_arcs else 0
    if not score.get("winner_reason"):
        score["winner_reason"] = "（自动选择综合得分最高的候选）"
    return score


def run_arc(after_chapter: int, *, n_candidates: int = 3,
            target_chapters: int = 100, user_hints: str = "") -> dict:
    arcs, ctx, cost_a = stage_a(after_chapter, n_candidates, target_chapters, user_hints)
    score, cost_b = stage_b(arcs, ctx, user_hints)
    with session_scope() as s:
        run = ArcRun(
            after_chapter=after_chapter,
            target_chapters=target_chapters,
            user_hints=user_hints or None,
            candidates_json=arcs,
            scores_json=score,
            chosen_index=score.get("winner_index"),
            cost_usd=cost_a + cost_b,
            created_at=datetime.utcnow(),
        )
        s.add(run)
        s.flush()
        return {
            "id": run.id,
            "candidates": arcs,
            "scores": score,
            "cost_usd": cost_a + cost_b,
        }


def list_runs(limit: int = 30) -> list[dict]:
    with session_scope() as s:
        rows = s.execute(
            select(ArcRun).order_by(desc(ArcRun.id)).limit(limit)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "after_chapter": r.after_chapter,
                "target_chapters": r.target_chapters,
                "user_hints": r.user_hints,
                "chosen_index": r.chosen_index,
                "cost_usd": r.cost_usd,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


def get_run(run_id: int) -> dict | None:
    with session_scope() as s:
        r = s.get(ArcRun, run_id)
        if not r:
            return None
        # Legacy rows (saved before the str-JSON fallback was added) may have
        # candidates_json stored as a JSON-encoded string. Coerce on read.
        cands = _coerce_list(r.candidates_json) if r.candidates_json is not None else []
        scores = r.scores_json or {}
        if isinstance(scores, str):
            try:
                scores = json.loads(scores)
            except json.JSONDecodeError:
                scores = {}
        if isinstance(scores, dict):
            scores = dict(scores)
            scores["scores"] = _coerce_list(scores.get("scores", []))
        return {
            "id": r.id,
            "after_chapter": r.after_chapter,
            "target_chapters": r.target_chapters,
            "user_hints": r.user_hints,
            "candidates": cands,
            "scores": scores,
            "chosen_index": r.chosen_index,
            "cost_usd": r.cost_usd,
        }
