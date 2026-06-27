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


def _single_arc_schema() -> dict:
    """单候选 schema：把 ARC_TOOL 里 arcs 数组的 item 提为顶层对象。"""
    item = ARC_TOOL["input_schema"]["properties"]["arcs"]["items"]
    return {"type": "object", "properties": item.get("properties", {}),
            "required": ["title", "theme", "phases"]}


def _loads_arc_obj(text: str) -> dict | None:
    """从 content 解析**单个** arc 对象（容错 json_repair；兼容被包成 {arcs:[..]} 或数组）。"""
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
    if isinstance(obj, dict):
        if "title" not in obj and isinstance(obj.get("arcs"), list) and obj["arcs"]:
            return obj["arcs"][0]
        return obj
    if isinstance(obj, list) and obj:
        return obj[0]
    return None


def _valid_arc(a: Any) -> bool:
    """完整候选的最低标准：有非空 title 且至少 1 个阶段。否则视为碎片，丢弃。"""
    return (isinstance(a, dict) and bool(str(a.get("title", "")).strip())
            and len(_coerce_list(a.get("phases", []))) > 0)


def _stage_a_oneshot(ctx: dict, blocks: list, after_chapter: int, n_candidates: int,
                     target_chapters: int, user_hints: str) -> tuple[list[dict], dict, float]:
    """一次性生成 N 个候选——短章/记忆不大时更快(1 次调用)。

    注意：长章 + 丰富记忆的重上下文下，大嵌套多候选 JSON 易写崩→被 json_repair
    打散成残片(改进记录 #21)。故此模式适合短章书；长章书用逐候选模式。
    仍套用 `_valid_arc` 过滤,残片不入库。
    """
    system_chain: list[Any] = [
        {"type": "text", "text": ARC_SYSTEM + _schema_json_hint(ARC_TOOL["input_schema"])}, *blocks]
    if user_hints.strip():
        system_chain.append({"type": "text", "text": (
            "【用户创作偏好（导演备注 — 高优先级）】\n" + user_hints.strip()
            + "\n\n请让所有候选都明确反映上述偏好；偏好与硬约束冲突时硬约束优先。")})
    open_count = len(ctx["open_foreshadowings"])
    user = (
        f"已写到第 {after_chapter} 章。请提出 {n_candidates} 个**风格迥异、方向各不相同**的"
        f"完整故事弧候选，每个预计延展约 {target_chapters} 章。\n"
        f"当前有 {open_count} 条 open 伏笔——请尽量在阶段中覆盖至少 70%。\n"
        "记得用 foreshadow_ids_addressed 在每个阶段标注收束的伏笔 id。"
    )
    if user_hints.strip():
        user += "\n\n再次强调：每个候选都必须显式体现 system 中【用户创作偏好】里的方向。"
    resp = llm.call(agent="arc.diverge", model=MODEL_STRONG, system=system_chain,
                    messages=[{"role": "user", "content": user}],
                    max_tokens=16000, temperature=0.95, top_p=0.95)
    arcs = _coerce_list((resp.tool_use or {}).get("input", {}).get("arcs", []))
    if not arcs and resp.text:
        parsed = _extract_json_from_text(resp.text, "arcs")
        if isinstance(parsed, list):
            arcs = parsed
    arcs = [a for a in arcs if _valid_arc(a)]   # 过滤碎片(两种模式通用)
    for a in arcs:
        a["phases"] = _coerce_list(a.get("phases", []))
    return arcs, ctx, resp.cost_usd


def stage_a(after_chapter: int, n_candidates: int, target_chapters: int,
            user_hints: str = "", per_candidate: bool = True) -> tuple[list[dict], dict, float]:
    """生成 N 个故事弧候选。`per_candidate=True`(默认)逐个生成(长章/重记忆稳);
    `False` 一次性生成(短章快)。两种模式都过滤碎片(`_valid_arc`)。"""
    ctx = _gather_context(after_chapter)
    blocks = _ctx_blocks(ctx)
    if not per_candidate:
        return _stage_a_oneshot(ctx, blocks, after_chapter, n_candidates, target_chapters, user_hints)
    open_count = len(ctx["open_foreshadowings"])
    single_schema = _single_arc_schema()
    arcs: list[dict] = []
    total_cost = 0.0
    import logging
    log = logging.getLogger("arc")

    # 逐个生成,直到凑够 n_candidates 个**有效**候选;给少量额外尝试容忍偶发坏 JSON。
    target = max(1, n_candidates)
    max_attempts = target + 3
    attempt = 0
    while len(arcs) < target and attempt < max_attempts:
        i = len(arcs)
        attempt += 1
        sys_head = (ARC_SYSTEM
                    + "\n\n# 本次只产出【1 个】完整故事弧候选——单个 JSON 对象，"
                      "不要数组、不要一次给多个。"
                    + _schema_json_hint(single_schema))
        system_chain: list[Any] = [{"type": "text", "text": sys_head}, *blocks]
        if user_hints.strip():
            system_chain.append({
                "type": "text",
                "text": ("【用户创作偏好（导演备注 — 高优先级）】\n" + user_hints.strip()
                         + "\n\n本候选必须明确反映上述偏好；与硬约束冲突时硬约束优先。"),
            })
        prior = [str(a.get("title", "")).strip() for a in arcs if a.get("title")]
        user = (
            f"已写到第 {after_chapter} 章。请产出**第 {i + 1}/{n_candidates} 个**完整故事弧候选"
            f"（只 1 个），预计延展约 {target_chapters} 章。\n"
            f"当前有 {open_count} 条 open 伏笔——阶段中尽量覆盖至少 70%，"
            "用 foreshadow_ids_addressed 在每个阶段标注收束的伏笔 id。\n"
        )
        if prior:
            user += f"已有候选（本候选务必与它们风格/走向迥异，不得重复）：{'；'.join(prior)}\n"
        if user_hints.strip():
            user += "再次强调：本候选必须显式体现 system 中【用户创作偏好】。\n"

        resp = llm.call(
            agent="arc.diverge",
            model=MODEL_STRONG,
            system=system_chain,
            messages=[{"role": "user", "content": user}],
            max_tokens=12000,
            temperature=0.95,
            top_p=0.95,
        )
        total_cost += resp.cost_usd
        arc = (resp.tool_use or {}).get("input") or {}
        if not _valid_arc(arc):
            arc = _loads_arc_obj(resp.text) or arc
        if _valid_arc(arc):
            arc["phases"] = _coerce_list(arc.get("phases", []))
            arcs.append(arc)
        else:
            log.warning("arc.diverge 第 %d 个候选无效(无title/phases)；text(300)=%s",
                        i + 1, (resp.text or "")[:300])
    return arcs, ctx, total_cost


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
    # 修复 D3(红蓝对抗):此处必须用 ARC_SCORING_TOOL 真实的 5 个维度名。
    # 旧代码用的是 prediction 链路的旧维度名(coherence/foreshadow_use/…),
    # 与 arc 评分 schema 仅 novelty 重合 → 兜底退化成"纯按新颖度选 winner",
    # macro_coherence/evidence_quality 完全不参与。详见 docs/架构红蓝对抗-质疑与验证.md。
    dims = ("macro_coherence", "evidence_quality", "foreshadow_coverage", "hero_arc", "novelty")
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
            target_chapters: int = 100, user_hints: str = "",
            per_candidate: bool = True) -> dict:
    arcs, ctx, cost_a = stage_a(after_chapter, n_candidates, target_chapters,
                                user_hints, per_candidate=per_candidate)
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
