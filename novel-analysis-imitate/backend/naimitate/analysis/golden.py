"""Phase 1 · golden_finger_step 分析层:主角『金手指/外挂』升级台阶(升级斜率)。

逐批扫原文,抽出主角实力/能力发生质变的台阶:新能力、触发方式、与当前对手的差距。
聚合出升级节律(平均隔多少章升一级、触发方式分布、是否长期碾压/被压)。
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from sqlalchemy import select, text as _sql_text, delete  # noqa: E402
from app.config import MODEL_FAST  # noqa: E402
from app.db import get_engine, session_scope  # noqa: E402
from app.books import library  # noqa: E402
from app.llm import client as llm  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402
from . import models as M  # noqa: E402

TRIGGERS = ["奇遇", "苦修", "危机逼出", "反派馈赠", "血脉觉醒", "顿悟", "外力相助", "其他"]
GAPS = ["碾压", "略胜", "持平", "落后", "悬殊", "未知"]

_ITEM = {
    "type": "object",
    "properties": {
        "chapter_number": {"type": "integer"},
        "power_tier": {"type": "string"},
        "new_capability": {"type": "string"},
        "trigger": {"type": "string", "enum": TRIGGERS},
        "gap_vs_antagonist": {"type": "string", "enum": GAPS},
        "summary": {"type": "string"},
    },
    "required": ["chapter_number", "power_tier", "new_capability", "trigger",
                 "gap_vs_antagonist", "summary"],
    "additionalProperties": False,
}
_SCHEMA = {"type": "object", "properties": {"steps": {"type": "array", "items": _ITEM}},
           "required": ["steps"], "additionalProperties": False}


def _rf() -> dict:
    return {"type": "json_schema",
            "json_schema": {"name": "golden_finger_steps", "strict": True, "schema": _SCHEMA}}


_SYS = (
    "你是中文小说的『主角成长线分析师』。给你若干章原文,找出本批次中**主角实力/核心能力发生质变**的台阶。\n"
    "只记真正的升级/质变(新境界、新能力、外挂进化),不记普通战斗。一批可能 0 条或多条。\n"
    "- power_tier:升级后的境界/层级名(若无明确体系,用一句话描述当前实力档位)。\n"
    "- new_capability:本台阶解锁的新能力。\n"
    f"- trigger 取其一:{'/'.join(TRIGGERS)}。\n"
    f"- gap_vs_antagonist 取其一:{'/'.join(GAPS)}(升级后相对当前主要对手的实力差)。\n"
    "- summary:一句话概括。\n"
    "chapter_number 必须是给定章节号之一。"
)


def _strip(s: str) -> str:
    return re.sub(r"```json|```", "", s or "").strip()


def _loads(resp) -> list:
    tu = (resp.tool_use or {}).get("input")
    if isinstance(tu, dict) and isinstance(tu.get("steps"), list):
        return tu["steps"]
    try:
        from json_repair import repair_json
        d = json.loads(repair_json(_strip(resp.text)))
    except Exception:
        return []
    if isinstance(d, dict) and isinstance(d.get("steps"), list):
        return d["steps"]
    if isinstance(d, list):
        return d
    return []


def _to_num(v, fallback=None):
    if isinstance(v, int):
        return v
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else fallback


def _chapters(head: int = 1400, tail: int = 400) -> list[dict]:
    with get_engine().begin() as conn:
        rows = conn.execute(_sql_text(
            "SELECT chapter, title, body FROM chapter_fts WHERE body IS NOT NULL "
            "AND chapter IS NOT NULL ORDER BY chapter")).mappings().all()
    out = []
    for r in rows:
        b = (r.get("body") or "").strip()
        if not b:
            continue
        txt = b if len(b) <= head + tail else (b[:head] + "\n……\n" + b[-tail:])
        out.append({"chapter": r["chapter"], "title": r.get("title") or "", "text": txt})
    return out


def tag_steps(slug: str, *, batch_size: int = 8, max_chapters: int | None = None,
              replace: bool = True) -> dict:
    library.set_active(slug)
    init_schema()
    chs = _chapters()
    if max_chapters:
        chs = chs[:max_chapters]
    if not chs:
        return {"error": "no chapters", "steps": 0}
    valid = {c["chapter"] for c in chs}
    if replace:
        with session_scope() as s:
            s.execute(delete(M.GoldenFingerStep))
    total, cost = 0, 0.0
    batches = [chs[i:i + batch_size] for i in range(0, len(chs), batch_size)]
    for bi, batch in enumerate(batches):
        nums = "、".join(str(c["chapter"]) for c in batch)
        body = "\n\n".join(f"【第{c['chapter']}章 {c['title']}】\n{c['text']}" for c in batch)
        try:
            resp = llm.call(agent="analysis.golden", model=MODEL_FAST,
                            system=[{"type": "text", "text": _SYS
                                     + "\n\n# 输出格式\n只输出 JSON 对象 {\"steps\":[...]}。无升级则空数组。"}],
                            messages=[{"role": "user", "content":
                                       f"分析第 {nums} 章的主角升级台阶。\n\n{body}"}],
                            max_tokens=4000, temperature=0.2, response_format=_rf())
            cost += resp.cost_usd or 0.0
            steps = _loads(resp)
        except Exception as e:  # noqa: BLE001
            print(f"[analysis.golden] batch {bi} 失败: {str(e)[:120]}", flush=True)
            continue
        rows = []
        for st in steps:
            if not isinstance(st, dict):
                continue
            cn = _to_num(st.get("chapter_number"), batch[0]["chapter"])
            cap = (st.get("new_capability") or "").strip()
            if cn not in valid or not cap:
                continue
            tg, gp = st.get("trigger"), st.get("gap_vs_antagonist")
            rows.append(M.GoldenFingerStep(
                chapter=int(cn),
                power_tier=(st.get("power_tier") or "")[:60],
                new_capability=cap[:120],
                trigger=tg if tg in TRIGGERS else "其他",
                gap_vs_antagonist=gp if gp in GAPS else "未知",
                summary=(st.get("summary") or "")[:300],
                created_at=datetime.utcnow()))
        if rows:
            with session_scope() as s:
                for r in rows:
                    s.add(r)
            total += len(rows)
        print(f"[analysis.golden] {slug} batch {bi+1}/{len(batches)} "
              f"ch{batch[0]['chapter']}-{batch[-1]['chapter']}: +{len(rows)} (累计 {total})", flush=True)
    summarize(slug)
    return {"steps": total, "batches": len(batches), "cost_usd": round(cost, 4)}


def summarize(slug: str) -> dict:
    library.set_active(slug)
    init_schema()
    with session_scope() as s:
        rows = s.execute(select(M.GoldenFingerStep).order_by(M.GoldenFingerStep.chapter)).scalars().all()
        if not rows:
            return {"error": "no steps"}
        chs = [r.chapter for r in rows]
        gaps_seq = [{"chapter": chs[i + 1] - chs[i]} for i in range(len(chs) - 1)]
        avg_gap = round(sum(g["chapter"] for g in gaps_seq) / len(gaps_seq), 1) if gaps_seq else 0
        trig_dist: dict[str, int] = {}
        for r in rows:
            trig_dist[r.trigger or "其他"] = trig_dist.get(r.trigger or "其他", 0) + 1
        gap_dist: dict[str, int] = {}
        for r in rows:
            gap_dist[r.gap_vs_antagonist or "未知"] = gap_dist.get(r.gap_vs_antagonist or "未知", 0) + 1
        card = {
            "n_steps": len(rows),
            "avg_chapters_per_upgrade": avg_gap,
            "trigger_distribution": trig_dist,
            "power_gap_distribution": gap_dist,
            "ladder": [{"chapter": r.chapter, "tier": r.power_tier,
                        "capability": r.new_capability} for r in rows],
        }
        row = s.get(M.AnalysisCard, "golden_finger")
        if not row:
            row = M.AnalysisCard(category="golden_finger")
            s.add(row)
        row.card_json = card
        row.updated_at = datetime.utcnow()
    return {"slug": slug, "card": card}


def get_steps(slug: str) -> dict:
    library.set_active(slug)
    init_schema()
    with session_scope() as s:
        rows = s.execute(select(M.GoldenFingerStep).order_by(M.GoldenFingerStep.chapter)).scalars().all()
        card = s.get(M.AnalysisCard, "golden_finger")
        return {
            "slug": slug,
            "steps": [{"chapter": r.chapter, "power_tier": r.power_tier,
                       "new_capability": r.new_capability, "trigger": r.trigger,
                       "gap_vs_antagonist": r.gap_vs_antagonist, "summary": r.summary} for r in rows],
            "golden_card": card.card_json if card else None,
        }
