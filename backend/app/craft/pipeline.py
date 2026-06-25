"""笔法片段库抽取管线(09-笔法片段库与拆解)。

两段式:
  1) tag_chapters —— 便宜模型(MODEL_FAST)逐批扫全书章节,抽出三类典型片段,落
     craft_snippet(每类留全部,不截断)。
  2) build_style_cards —— 强模型(MODEL_STRONG)对每类片段做风格拆解,落 craft_style_card。

健壮性沿用本仓约定:JSON-in-text + 围栏剥离 + json_repair;单批/单类失败不连累其它;
串行执行避免 429。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import delete, desc, select, text as _sql_text

from ..config import MODEL_FAST, MODEL_STRONG
from ..db import get_engine, session_scope
from ..llm import client as llm
from ..llm.prompts.craft import (
    CRAFT_CARD_TOOL,
    CRAFT_CARD_SYSTEM,
    CRAFT_CATEGORIES,
    CRAFT_TAG_TOOL,
    CRAFT_TAG_SYSTEM,
    build_card_user,
    build_tag_user,
    craft_tag_response_format,
    schema_hint,
)
from ..memory.models import CraftSnippet, CraftStyleCard
from ..memory.schema_init import init_schema

MVP_CATEGORIES = list(CRAFT_CATEGORIES)        # combat / dialogue_subtext / hook
_PER_CHAPTER_CAP = 2800                          # 每章喂入字数上限(控批量 token)
_DEFAULT_BATCH = 5                               # 每批章数
_CARD_MAX_SNIPPETS = 24                          # 拆解卡每类最多喂入的片段数(取高分)


def _strip_fences(s: str) -> str:
    return re.sub(r"```json|```", "", s or "").strip()


def _loads_obj(resp) -> dict:
    """tool_use 优先,回落 json_repair(先剥围栏)。返回 dict。"""
    tu = (resp.tool_use or {}).get("input")
    if isinstance(tu, dict) and tu:
        return tu
    if resp.text:
        try:
            from json_repair import repair_json
            d = json.loads(repair_json(_strip_fences(resp.text)))
            if isinstance(d, dict):
                return d
            if isinstance(d, list) and d and isinstance(d[0], dict):
                return {"snippets": d}
        except Exception:
            pass
    return {}


def _all_chapters() -> list[dict]:
    with get_engine().begin() as conn:
        rows = conn.execute(
            _sql_text("SELECT chapter, title, body FROM chapter_fts "
                      "WHERE body IS NOT NULL AND chapter IS NOT NULL ORDER BY chapter")
        ).mappings().all()
    out = []
    for r in rows:
        body = (r.get("body") or "").strip()
        if not body:
            continue
        out.append({"chapter": r["chapter"], "title": r.get("title") or "",
                    "text": body[:_PER_CHAPTER_CAP]})
    return out


def tag_chapters(*, batch_size: int = _DEFAULT_BATCH, max_chapters: int | None = None,
                 replace: bool = True) -> dict[str, Any]:
    """逐批扫章节、抽三类片段、落 craft_snippet。replace=True 先清空旧片段(重抽)。"""
    init_schema()
    chapters = _all_chapters()
    if max_chapters:
        chapters = chapters[:max_chapters]
    if not chapters:
        return {"error": "no chapters — run split/extract first", "snippets": 0}

    if replace:
        with session_scope() as s:
            s.execute(delete(CraftSnippet))

    valid_ch = {c["chapter"] for c in chapters}
    total_cost = 0.0
    total = 0
    by_cat: dict[str, int] = {}
    batches = [chapters[i:i + batch_size] for i in range(0, len(chapters), batch_size)]
    for bi, batch in enumerate(batches):
        try:
            resp = llm.call(
                agent="craft.tag", model=MODEL_FAST,
                system=[{"type": "text", "text": CRAFT_TAG_SYSTEM + schema_hint(CRAFT_TAG_TOOL)}],
                messages=[{"role": "user", "content": build_tag_user(batch)}],
                max_tokens=8000, temperature=0.3,
                # json_schema strict:白名单模型(doubao-seed-2.0-pro/lite)上强制结构合规
                # (0 不合规);非白名单自动回落 JSON-in-text(见 client 白名单)。
                response_format=craft_tag_response_format(),
            )
            total_cost += resp.cost_usd or 0.0
            snips = _loads_obj(resp).get("snippets") or []
        except Exception as e:  # noqa: BLE001 — 单批失败不中断
            print(f"[craft.tag] batch {bi} 失败: {str(e)[:120]}", flush=True)
            continue

        rows = []
        for sn in snips:
            if not isinstance(sn, dict):
                continue
            cat = sn.get("category")
            ex = (sn.get("excerpt") or "").strip()
            ch = sn.get("chapter_number")
            if cat not in MVP_CATEGORIES or not ex or ch not in valid_ch:
                continue
            tags = sn.get("tags")
            rows.append(CraftSnippet(
                category=cat, subtype=(sn.get("subtype") or None),
                chapter_number=int(ch), excerpt=ex[:1200],
                representativeness=int(sn.get("representativeness") or 50),
                tags_json=tags if isinstance(tags, list) else [],
                created_at=datetime.utcnow(),
            ))
            by_cat[cat] = by_cat.get(cat, 0) + 1
            total += 1
        if rows:
            with session_scope() as s:
                s.add_all(rows)
        print(f"[craft.tag] batch {bi+1}/{len(batches)} ch{batch[0]['chapter']}-{batch[-1]['chapter']}: +{len(rows)} (累计 {total})", flush=True)

    return {"snippets": total, "by_category": by_cat, "batches": len(batches), "cost_usd": round(total_cost, 4)}


def build_style_cards() -> dict[str, Any]:
    """对每个 MVP 类别,取其(高分)片段做风格拆解,落 craft_style_card。"""
    init_schema()
    total_cost = 0.0
    done = {}
    for cat in MVP_CATEGORIES:
        with session_scope() as s:
            snips = s.execute(
                select(CraftSnippet).where(CraftSnippet.category == cat)
                .order_by(desc(CraftSnippet.representativeness)).limit(_CARD_MAX_SNIPPETS)
            ).scalars().all()
            cnt = s.execute(select(CraftSnippet).where(CraftSnippet.category == cat)).scalars().all()
            n_total = len(cnt)
            sample = [{"chapter_number": x.chapter_number, "subtype": x.subtype, "excerpt": x.excerpt} for x in snips]
        if not sample:
            done[cat] = {"snippet_count": 0, "card": None}
            continue
        try:
            resp = llm.call(
                agent="craft.card", model=MODEL_STRONG,
                system=[{"type": "text", "text": CRAFT_CARD_SYSTEM + schema_hint(CRAFT_CARD_TOOL)}],
                messages=[{"role": "user", "content": build_card_user(cat, sample)}],
                max_tokens=4000, temperature=0.3,
            )
            total_cost += resp.cost_usd or 0.0
            card = _loads_obj(resp)
        except Exception as e:  # noqa: BLE001
            print(f"[craft.card] {cat} 失败: {str(e)[:120]}", flush=True)
            done[cat] = {"snippet_count": n_total, "card": None, "error": str(e)[:120]}
            continue
        with session_scope() as s:
            row = s.execute(select(CraftStyleCard).where(CraftStyleCard.category == cat)).scalars().first()
            if not row:
                row = CraftStyleCard(category=cat)
                s.add(row)
            row.snippet_count = n_total
            row.card_json = card
            row.cost_usd = resp.cost_usd or 0.0
            row.updated_at = datetime.utcnow()
        done[cat] = {"snippet_count": n_total, "card": card}
        print(f"[craft.card] {cat}: 拆解完成(基于 {len(sample)}/{n_total} 片段)", flush=True)
    return {"cards": done, "cost_usd": round(total_cost, 4)}


def extract_all(*, batch_size: int = _DEFAULT_BATCH, max_chapters: int | None = None) -> dict[str, Any]:
    tagged = tag_chapters(batch_size=batch_size, max_chapters=max_chapters, replace=True)
    cards = build_style_cards()
    return {"tagged": tagged, "cards": cards.get("cards"), "cost_usd": round((tagged.get("cost_usd") or 0) + (cards.get("cost_usd") or 0), 4)}


# ---- 读取(给前端 / 写作 few-shot) ----

def categories_summary() -> dict[str, Any]:
    with session_scope() as s:
        out = {}
        for cat in MVP_CATEGORIES:
            rows = s.execute(select(CraftSnippet).where(CraftSnippet.category == cat)).scalars().all()
            sub: dict[str, int] = {}
            for r in rows:
                sub[r.subtype or "-"] = sub.get(r.subtype or "-", 0) + 1
            card = s.execute(select(CraftStyleCard).where(CraftStyleCard.category == cat)).scalars().first()
            out[cat] = {"label": CRAFT_CATEGORIES[cat], "count": len(rows), "subtypes": sub,
                        "has_card": bool(card and card.card_json)}
    return out


def list_snippets(category: str | None = None, limit: int = 500) -> list[dict]:
    with session_scope() as s:
        q = select(CraftSnippet)
        if category:
            q = q.where(CraftSnippet.category == category)
        q = q.order_by(desc(CraftSnippet.representativeness), CraftSnippet.chapter_number).limit(limit)
        return [{"id": r.id, "category": r.category, "subtype": r.subtype,
                 "chapter_number": r.chapter_number, "excerpt": r.excerpt,
                 "representativeness": r.representativeness, "tags": r.tags_json or []}
                for r in s.execute(q).scalars().all()]


def get_cards() -> list[dict]:
    with session_scope() as s:
        return [{"category": r.category, "label": CRAFT_CATEGORIES.get(r.category, r.category),
                 "snippet_count": r.snippet_count, "card": r.card_json,
                 "updated_at": r.updated_at.isoformat() if r.updated_at else None}
                for r in s.execute(select(CraftStyleCard)).scalars().all()]


def fewshot_block(category: str, n: int = 3) -> str | None:
    """供写作 agent 注入:某类的风格卡要点 + 高分范例片段。无则 None。"""
    with session_scope() as s:
        card = s.execute(select(CraftStyleCard).where(CraftStyleCard.category == category)).scalars().first()
        snips = s.execute(
            select(CraftSnippet).where(CraftSnippet.category == category)
            .order_by(desc(CraftSnippet.representativeness)).limit(n)
        ).scalars().all()
        if not card and not snips:
            return None
        parts = [f"【本书「{CRAFT_CATEGORIES.get(category, category)}」笔法范式】"]
        if card and card.card_json:
            cj = card.card_json
            for k in ("summary", "sentence_rhythm", "rhetoric_density", "info_pacing", "structure_template"):
                if cj.get(k):
                    parts.append(f"- {k}: {cj[k]}")
            if cj.get("do"):
                parts.append("- 该做: " + "；".join(str(x) for x in cj["do"][:5]))
            if cj.get("dont"):
                parts.append("- 避免: " + "；".join(str(x) for x in cj["dont"][:5]))
        for i, sp in enumerate(snips):
            parts.append(f"【范例{i+1}·第{sp.chapter_number}章】\n{sp.excerpt}")
        return "\n".join(parts)
