"""Phase 1 · worldview_reveal 分析层:世界观设定的『揭示事件』时间轴。

江南式宏大世界观的精髓在『怎么把设定喂给读者而不显生硬』——本层逐批扫原文,
抽出每一次设定/概念的揭示:用什么手法、是否信息倾倒、埋设到兑现隔多远。聚合出
『铺垫节奏卡』(信息倾倒率、揭示手法分布、平均埋设跨度、重大设定揭示章)。

复用现有 LLM 客户端;小米/火山均走结构化输出(client 自动按模型降级 json_object)。
"""
from __future__ import annotations

import json
import re
import statistics
from datetime import datetime

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from sqlalchemy import select, text as _sql_text, delete  # noqa: E402
from app.config import MODEL_FAST  # noqa: E402
from app.db import get_engine, session_scope  # noqa: E402
from app.books import library  # noqa: E402
from app.llm import client as llm  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402
from . import models as M  # noqa: E402  注册新表到 Base

REVEAL_METHODS = ["对话", "情节体验", "旁白直述", "文献档案", "回忆", "环境暗示", "角色独白", "其他"]

_REVEAL_ITEM = {
    "type": "object",
    "properties": {
        "chapter_number": {"type": "integer"},
        "concept": {"type": "string"},
        "reveal_method": {"type": "string", "enum": REVEAL_METHODS},
        "is_infodump": {"type": "boolean"},
        "setup_payoff_gap": {"type": "integer"},
        "importance": {"type": "integer"},
        "excerpt": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["chapter_number", "concept", "reveal_method", "is_infodump",
                 "setup_payoff_gap", "importance", "excerpt", "summary"],
    "additionalProperties": False,
}
_SCHEMA = {"type": "object",
           "properties": {"reveals": {"type": "array", "items": _REVEAL_ITEM}},
           "required": ["reveals"], "additionalProperties": False}


def _rf() -> dict:
    return {"type": "json_schema",
            "json_schema": {"name": "worldview_reveals", "strict": True, "schema": _SCHEMA}}


_SYS = (
    "你是中文小说的『世界观铺垫分析师』。给你若干章原文,找出本批次中**对读者首次/重要揭示设定**的瞬间。\n"
    "只记『设定/世界观/规则/势力/体系/概念』层面的揭示,不记普通剧情。一批可能 0 条,也可能多条。\n"
    "- concept:被揭示的设定名(如『序列体系』『真名禁忌』『神之眷者』)。\n"
    f"- reveal_method 取其一:{'/'.join(REVEAL_METHODS)}(作者用什么手法把它喂给读者)。\n"
    "- is_infodump:是否生硬信息倾倒(大段旁白/讲解,缺乏情节包裹)。\n"
    "- setup_payoff_gap:若此设定是为后文埋的伏笔,估计埋设到兑现隔多少章(无法判断填 0)。\n"
    "- importance 0-100:该设定对整本世界观的重要度。\n"
    "- excerpt:支撑判断的原文片段(<=200字,逐字摘录)。\n"
    "- summary:一句话——揭示了什么、用什么手法。\n"
    "chapter_number 必须是给定章节号之一。宁缺毋滥,只记真正的设定揭示。"
)


def _strip(s: str) -> str:
    return re.sub(r"```json|```", "", s or "").strip()


def _loads(resp) -> list:
    tu = (resp.tool_use or {}).get("input")
    if isinstance(tu, dict) and isinstance(tu.get("reveals"), list):
        return tu["reveals"]
    try:
        from json_repair import repair_json
        d = json.loads(repair_json(_strip(resp.text)))
    except Exception:
        return []
    if isinstance(d, dict) and isinstance(d.get("reveals"), list):
        return d["reveals"]
    if isinstance(d, list):
        return d
    if isinstance(d, dict) and d.get("concept"):
        return [d]
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


def tag_reveals(slug: str, *, batch_size: int = 6, max_chapters: int | None = None,
                replace: bool = True) -> dict:
    """逐批抽 worldview_reveal。串行避免 429。"""
    library.set_active(slug)
    init_schema()
    chs = _chapters()
    if max_chapters:
        chs = chs[:max_chapters]
    if not chs:
        return {"error": "no chapters — split/extract first", "reveals": 0}
    valid = {c["chapter"] for c in chs}
    if replace:
        with session_scope() as s:
            s.execute(delete(M.WorldviewReveal))
    total, cost = 0, 0.0
    batches = [chs[i:i + batch_size] for i in range(0, len(chs), batch_size)]
    for bi, batch in enumerate(batches):
        nums = "、".join(str(c["chapter"]) for c in batch)
        body = "\n\n".join(f"【第{c['chapter']}章 {c['title']}】\n{c['text']}" for c in batch)
        try:
            resp = llm.call(agent="analysis.worldview", model=MODEL_FAST,
                            system=[{"type": "text", "text": _SYS
                                     + "\n\n# 输出格式\n只输出一个 JSON 对象 {\"reveals\":[...]}。无揭示则 reveals 为空数组。"}],
                            messages=[{"role": "user", "content":
                                       f"分析第 {nums} 章的世界观揭示。\n\n{body}"}],
                            max_tokens=4000, temperature=0.2, response_format=_rf())
            cost += resp.cost_usd or 0.0
            reveals = _loads(resp)
        except Exception as e:  # noqa: BLE001
            print(f"[analysis.worldview] batch {bi} 失败: {str(e)[:120]}", flush=True)
            continue
        rows = []
        for rv in reveals:
            if not isinstance(rv, dict):
                continue
            cn = _to_num(rv.get("chapter_number"), batch[0]["chapter"])
            if cn not in valid:
                continue
            concept = (rv.get("concept") or "").strip()
            if not concept:
                continue
            rm = rv.get("reveal_method")
            rows.append(M.WorldviewReveal(
                chapter=int(cn),
                concept=concept[:80],
                reveal_method=rm if rm in REVEAL_METHODS else "其他",
                is_infodump=1 if rv.get("is_infodump") else 0,
                setup_payoff_gap=int(_to_num(rv.get("setup_payoff_gap"), 0) or 0),
                importance=max(0, min(100, int(_to_num(rv.get("importance"), 50) or 50))),
                excerpt=(rv.get("excerpt") or "")[:200],
                summary=(rv.get("summary") or "")[:300],
                created_at=datetime.utcnow()))
        if rows:
            with session_scope() as s:
                for r in rows:
                    s.add(r)
            total += len(rows)
        print(f"[analysis.worldview] {slug} batch {bi+1}/{len(batches)} "
              f"ch{batch[0]['chapter']}-{batch[-1]['chapter']}: +{len(rows)} (累计 {total})", flush=True)
    summarize(slug)
    return {"reveals": total, "batches": len(batches), "cost_usd": round(cost, 4)}


def summarize(slug: str) -> dict:
    """聚合『铺垫节奏卡』:信息倾倒率/手法分布/平均埋设跨度/重大设定揭示章/前期密度。"""
    library.set_active(slug)
    init_schema()
    with session_scope() as s:
        rows = s.execute(select(M.WorldviewReveal).order_by(M.WorldviewReveal.chapter)).scalars().all()
        if not rows:
            return {"error": "no reveals — run tag_reveals first"}
        n = len(rows)
        method_dist: dict[str, int] = {}
        for r in rows:
            method_dist[r.reveal_method or "其他"] = method_dist.get(r.reveal_method or "其他", 0) + 1
        infodump = sum(1 for r in rows if r.is_infodump)
        gaps = [r.setup_payoff_gap for r in rows if (r.setup_payoff_gap or 0) > 0]
        chapters = [r.chapter for r in rows]
        max_ch = max(chapters) if chapters else 1
        first_quarter = sum(1 for c in chapters if c <= max_ch * 0.25)
        major = [{"chapter": r.chapter, "concept": r.concept, "importance": r.importance}
                 for r in sorted(rows, key=lambda x: -(x.importance or 0))[:12]]
        card = {
            "n_reveals": n,
            "infodump_ratio": round(infodump / n, 2),
            "reveal_method_distribution": method_dist,
            "avg_setup_payoff_gap": round(statistics.mean(gaps), 1) if gaps else 0,
            "front_loaded_ratio": round(first_quarter / n, 2),   # 前 1/4 篇幅承载的设定占比
            "major_reveals": major,
        }
        row = s.get(M.AnalysisCard, "worldview")
        if not row:
            row = M.AnalysisCard(category="worldview")
            s.add(row)
        row.card_json = card
        row.updated_at = datetime.utcnow()
    return {"slug": slug, "card": card}


def get_reveals(slug: str) -> dict:
    library.set_active(slug)
    init_schema()
    with session_scope() as s:
        rows = s.execute(select(M.WorldviewReveal).order_by(M.WorldviewReveal.chapter)).scalars().all()
        card = s.get(M.AnalysisCard, "worldview")
        return {
            "slug": slug,
            "reveals": [{"chapter": r.chapter, "concept": r.concept,
                         "reveal_method": r.reveal_method, "is_infodump": r.is_infodump,
                         "setup_payoff_gap": r.setup_payoff_gap, "importance": r.importance,
                         "excerpt": r.excerpt, "summary": r.summary} for r in rows],
            "worldview_card": card.card_json if card else None,
        }
