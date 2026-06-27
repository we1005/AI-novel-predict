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
from ..llm.prompts.outline_refine import (
    OUTLINE_FLESH_SYSTEM,
    OUTLINE_FLESH_TOOL,
    OUTLINE_REFINE_SYSTEM,
    OUTLINE_REFINE_TOOL,
    OUTLINE_SKELETON_SYSTEM,
    OUTLINE_SKELETON_TOOL,
)
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


def _str_items(v: Any) -> list[str]:
    """把 must_include / key_events 等列表里偶发的 dict/非字符串元素强制成字符串
    (模型有时把条目返回成 {"事件": "..."} 这样的对象,下游 join/渲染会崩)。"""
    out: list[str] = []
    for x in _coerce_list(v):
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, dict):
            # 取常见值字段,否则整体 json 化
            picked = x.get("text") or x.get("event") or x.get("事件") or x.get("content")
            out.append(str(picked) if picked else json.dumps(x, ensure_ascii=False))
        elif x is not None:
            out.append(str(x))
    return out


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


def _extra_blocks(src: dict, combined_hints: str) -> list[dict]:
    """创作偏好 + 全弧元信息 system 块(两种模式共用)。"""
    extra: list[dict] = []
    if combined_hints:
        extra.append({"type": "text", "text": "【创作偏好】\n" + combined_hints})
    if src.get("arc_meta"):
        extra.append({"type": "text",
                      "text": "【全弧元信息（不可违背）】\n" + llm.stable_json(src["arc_meta"])})
    return extra


def _strip_fences(s: str) -> str:
    """去掉 ```json / ``` 围栏(模型常把 JSON 包在围栏里,json_repair 处理不干净)。"""
    import re
    return re.sub(r"```json|```", "", s or "").strip()


def _parse_chapters_field(resp) -> list:
    """从 resp 解析 {chapters:[...]}(tool_use 优先,回落 json_repair;先剥围栏)。"""
    chapters = _coerce_list((resp.tool_use or {}).get("input", {}).get("chapters", []))
    if not chapters and resp.text:
        try:
            from json_repair import repair_json
            decoded = json.loads(repair_json(_strip_fences(resp.text)))
            if isinstance(decoded, dict) and "chapters" in decoded:
                chapters = _coerce_list(decoded["chapters"])
            elif isinstance(decoded, list):
                chapters = decoded
        except Exception:
            pass
    return chapters


def _refine_oneshot(src: dict, blocks: list, extra: list, chapter_start: int,
                    chapter_end: int) -> tuple[list, float, int]:
    """一次性产出整段 phase 的全部章节大纲(原有行为)。"""
    # JSON-in-text, not forced tool_choice: outline uses the same ~89k-char
    # context as predict/arc, where doubao-code's forced tool_choice silently
    # returns empty tool_calls + empty content (改进记录 #14).
    hint = (
        "\n\n# 输出格式（严格 · 覆盖前述任何「调用工具」指示）\n"
        "只输出一个 JSON 对象，不要任何其它文字、不要 markdown 围栏。必须严格符合此 JSON Schema：\n"
        + json.dumps(OUTLINE_REFINE_TOOL["input_schema"], ensure_ascii=False)
    )
    system_chain: list[Any] = [{"type": "text", "text": OUTLINE_REFINE_SYSTEM + hint}, *blocks, *extra]
    user = (
        f"# 任务\n\n"
        f"为 phase「{src['phase_name']}」（章节范围 {chapter_start}–{chapter_end}，"
        f"约 {chapter_end - chapter_start + 1} 章）生成逐章大纲。\n\n"
        f"# Phase 元信息\n\n" + llm.stable_json(src["phase"])
        + "\n\n请严格按 phase 范围输出 chapter_index 递增的章节大纲。"
    )
    resp = llm.call(agent="outline.refine", model=MODEL_STRONG, system=system_chain,
                    messages=[{"role": "user", "content": user}],
                    max_tokens=12000, temperature=0.6)
    return _parse_chapters_field(resp), resp.cost_usd, resp.elapsed_ms


def _refine_stepwise(src: dict, blocks: list, extra: list, chapter_start: int,
                     chapter_end: int) -> tuple[list, float, int]:
    """骨架→填充:① 一次产整段轻量骨架 → ② 逐章展开(承接前序+预算管家)。"""
    import logging
    log = logging.getLogger("outline.stepwise")
    total_cost = 0.0
    total_ms = 0
    phase_meta = llm.stable_json(src["phase"])

    # ---- 遍 1:骨架 ----
    sk_hint = (
        "\n\n# 输出格式（严格 · 覆盖任何「调用工具」指示）\n"
        "只输出一个 JSON 对象,不要其它文字/围栏,严格符合此 Schema：\n"
        + json.dumps(OUTLINE_SKELETON_TOOL["input_schema"], ensure_ascii=False)
    )
    sk_system: list[Any] = [{"type": "text", "text": OUTLINE_SKELETON_SYSTEM + sk_hint}, *blocks, *extra]
    sk_user = (
        f"# 任务\n\n为 phase「{src['phase_name']}」（章节范围 {chapter_start}–{chapter_end}，"
        f"约 {chapter_end - chapter_start + 1} 章）切出逐章骨架。\n\n"
        f"# Phase 元信息\n\n" + phase_meta
        + f"\n\n请输出 {chapter_start}–{chapter_end} 范围内 chapter_index 递增的逐章骨架。"
    )
    # 骨架是 JSON-in-text,大上下文下偶发吐出 json_repair 救不回的内容→判空(同 arc 家族)。
    # 重试至多 2 次再降级,而不是一次空就放弃。
    skeleton: list[dict] = []
    for attempt in range(2):
        sk_resp = llm.call(agent="outline.skeleton", model=MODEL_STRONG, system=sk_system,
                           messages=[{"role": "user", "content": sk_user}],
                           max_tokens=8000, temperature=0.5 if attempt == 0 else 0.7)
        total_cost += sk_resp.cost_usd
        total_ms += sk_resp.elapsed_ms or 0
        skeleton = [c for c in _parse_chapters_field(sk_resp)
                    if isinstance(c, dict) and isinstance(c.get("chapter_index"), int) and c.get("title")]
        if skeleton:
            break
        log.warning("stepwise 骨架第 %d 次为空,重试", attempt + 1)
    skeleton.sort(key=lambda c: c["chapter_index"])
    if not skeleton:
        # 重试仍空:降级回一次性,保证有产出而非空。
        log.warning("stepwise 骨架重试后仍空,降级回 oneshot")
        return _refine_oneshot(src, blocks, extra, chapter_start, chapter_end)

    # ---- 遍 2:逐章填充 ----
    flesh_hint = (
        "\n\n# 输出格式（严格 · 覆盖任何「调用工具」指示）\n"
        "只输出一个 JSON 对象（单章）,不要其它文字/围栏,严格符合此 Schema：\n"
        + json.dumps(OUTLINE_FLESH_TOOL["input_schema"], ensure_ascii=False)
    )
    # phase 概要里待覆盖的 key_event(预算管家用)
    remaining_keys: list[str] = []
    pk = src["phase"].get("key_events") if isinstance(src.get("phase"), dict) else None
    if isinstance(pk, list):
        remaining_keys = [str(x) for x in pk]

    skeleton_brief = "\n".join(
        f"- 第{c['chapter_index']}章《{c.get('title')}》｜{c.get('intent','')}｜beat:{c.get('beat','')}"
        for c in skeleton
    )
    done: list[dict] = []
    n = len(skeleton)
    for i, sc in enumerate(skeleton):
        prev_brief = "（本章是 phase 首章，无前序）" if not done else "\n".join(
            f"- 第{d['chapter_index']}章《{d.get('title')}》｜钩子:{d.get('ending_hook') or '（未给）'}"
            f"｜核心:{('；'.join((d.get('key_events') or [])[:3]))}"
            for d in done[-3:]
        )
        flesh_system: list[Any] = [
            {"type": "text", "text": OUTLINE_FLESH_SYSTEM + flesh_hint},
            *blocks, *extra,
            {"type": "text", "text": "【整段骨架（全局视野）】\n" + skeleton_brief},
        ]
        flesh_user = (
            f"# Phase 元信息\n\n{phase_meta}\n\n"
            f"# 本章骨架条目（第 {i+1}/{n} 章）\n\n" + llm.stable_json(sc) + "\n\n"
            f"# 前序已定章节钩子\n\n{prev_brief}\n\n"
            f"# phase 尚需覆盖的 key_event（预算管家）\n\n"
            + ("；".join(remaining_keys) if remaining_keys else "（无显式清单，按骨架认领推进）")
            + f"\n\n请只展开 chapter_index={sc['chapter_index']} 这一章，承接上一章钩子，落实本章 beat。"
        )
        try:
            fr = llm.call(agent="outline.flesh", model=MODEL_STRONG, system=flesh_system,
                          messages=[{"role": "user", "content": flesh_user}],
                          max_tokens=4000, temperature=0.6)
            total_cost += fr.cost_usd
            total_ms += fr.elapsed_ms or 0
            obj = (fr.tool_use or {}).get("input") or {}
            if not (isinstance(obj, dict) and obj.get("title") and obj.get("must_include")):
                # 回落 json_repair 解析单对象
                try:
                    from json_repair import repair_json
                    dec = json.loads(repair_json(_strip_fences(fr.text or "")))
                    if isinstance(dec, dict):
                        obj = dec
                    elif isinstance(dec, list) and dec and isinstance(dec[0], dict):
                        obj = dec[0]
                except Exception:
                    obj = {}
        except Exception as e:  # noqa: BLE001 — 单章失败用骨架兜底,不中断整段
            log.warning("flesh 第 %d 章失败: %s", sc["chapter_index"], str(e)[:120])
            obj = {}

        if not (isinstance(obj, dict) and obj.get("title") and obj.get("must_include")):
            # 兜底:用骨架条目拼一个最小可用章,不留空洞
            # 修复 D5(红蓝对抗):打 is_fallback 标记,让占位章不再与正常章无法区分。
            # 下游(bookwriter/前端)可据此告警/复跑,而非把"模型失败"静默当成"合理大纲"。
            # 详见 docs/架构红蓝对抗-质疑与验证.md。
            obj = {
                "title": sc.get("title"),
                "intent": sc.get("intent", ""),
                "must_include": [sc.get("beat")] if sc.get("beat") else ["（待补充）"],
                "key_events": [sc.get("beat")] if sc.get("beat") else [],
                "pacing": "（待补充）",
                "word_target": 3000,
                "foreshadow_ids_addressed": sc.get("foreshadow_ids", []),
                "is_fallback": True,
                "fallback_reason": "单章 flesh 失败或解析为空,已用骨架拼最小章——质量信号,建议复跑或人工补全",
            }
        obj["chapter_index"] = sc["chapter_index"]  # 强制对齐骨架编号
        # 列表字段强制成字符串(模型偶把条目返回成 dict,会让 join/渲染/落库崩)
        obj["must_include"] = _str_items(obj.get("must_include"))
        obj["key_events"] = _str_items(obj.get("key_events"))
        if obj.get("must_avoid") is not None:
            obj["must_avoid"] = _str_items(obj.get("must_avoid"))
        # 从待覆盖清单里划掉本章认领的 key_event
        for k in (sc.get("key_event_refs") or []):
            if str(k) in remaining_keys:
                remaining_keys.remove(str(k))
        done.append(obj)

    return done, total_cost, total_ms


def refine(*, source_kind: str, source_run_id: int, chosen_index: int,
           phase_index: int | None = None,
           user_hints: str = "",
           chapter_start_override: int | None = None,
           chapter_end_override: int | None = None,
           continuity_hint: str | None = None,
           mode: str = "oneshot",
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
    combined_hints = "\n".join([h for h in [src.get("user_hints"), user_hints] if h]).strip()
    extra = _extra_blocks(src, combined_hints)

    if mode == "stepwise":
        chapters, cost_usd, elapsed_ms = _refine_stepwise(src, blocks, extra, chapter_start, chapter_end)
    else:
        chapters, cost_usd, elapsed_ms = _refine_oneshot(src, blocks, extra, chapter_start, chapter_end)

    # Filter out items that lost critical fields.
    chapters = [
        c for c in chapters
        if isinstance(c, dict) and isinstance(c.get("chapter_index"), int)
        and c.get("title") and c.get("must_include")
    ]
    # 列表字段强制成字符串(两模式通用:oneshot 偶尔也把条目返回成 dict)
    for c in chapters:
        c["must_include"] = _str_items(c.get("must_include"))
        c["key_events"] = _str_items(c.get("key_events"))
        if c.get("must_avoid") is not None:
            c["must_avoid"] = _str_items(c.get("must_avoid"))
    chapters.sort(key=lambda c: c["chapter_index"])

    if not persist:
        # Whole-book projection aggregates phases itself; don't spam OutlineRun list.
        return {
            "id": None, "source_kind": source_kind, "source_run_id": source_run_id,
            "source_chosen_index": chosen_index, "phase_index": phase_index or 0,
            "phase_name": src.get("phase_name"), "chapter_start": chapter_start,
            "chapter_end": chapter_end, "chapters": chapters,
            "cost_usd": cost_usd, "elapsed_ms": elapsed_ms,
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
            cost_usd=cost_usd,
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
            "cost_usd": cost_usd,
            "elapsed_ms": elapsed_ms,
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
