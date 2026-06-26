"""Phase 1 · chapter_beat 分析层:逐章节拍(张力/场景类型/POV/plot_function/章末钩子)。

复用现有 LLM 客户端 + 火山 json_schema strict(白名单模型)。按书存进该书 novel.db 的
chapter_beat 表;聚合出张力曲线/场景分布/POV 占比/高潮章,落 analysis_card('pacing')。
"""
from __future__ import annotations

import json
import re
import statistics
from datetime import datetime

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from sqlalchemy import select, text as _sql_text, delete  # noqa: E402
from app.config import MODEL_FAST, MODEL_STRONG  # noqa: E402
from app.db import get_engine, session_scope  # noqa: E402
from app.books import library  # noqa: E402
from app.llm import client as llm  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402
from . import models as M  # noqa: E402  注册 ChapterBeat/AnalysisCard 到 Base

SCENE_TYPES = ["铺垫", "小高潮", "大高潮", "热血", "悬疑惊悚", "煽情", "日常", "转场", "其他"]
PLOT_FUNCS = ["setup", "escalation", "payoff", "twist", "breather"]

_BEAT_ITEM = {
    "type": "object",
    "properties": {
        "chapter_number": {"type": "integer"},
        "tension_level": {"type": "integer"},
        "scene_type": {"type": "string", "enum": SCENE_TYPES},
        "pov_holder": {"type": "string"},
        "is_protagonist_pov": {"type": "boolean"},
        "plot_function": {"type": "string", "enum": PLOT_FUNCS},
        "hook_type": {"type": "string"},
        "cliffhanger_strength": {"type": "integer"},
        "summary": {"type": "string"},
    },
    "required": ["chapter_number", "tension_level", "scene_type", "pov_holder",
                 "is_protagonist_pov", "plot_function", "hook_type",
                 "cliffhanger_strength", "summary"],
    "additionalProperties": False,
}
_BEAT_SCHEMA = {"type": "object",
                "properties": {"beats": {"type": "array", "items": _BEAT_ITEM}},
                "required": ["beats"], "additionalProperties": False}


def _beat_rf() -> dict:
    return {"type": "json_schema",
            "json_schema": {"name": "chapter_beats", "strict": True, "schema": _BEAT_SCHEMA}}


_SYS = (
    "你是中文小说的『叙事节拍分析师』。给你若干章原文(每章给开头+结尾),为**每一章**判定其节拍。\n"
    "- tension_level 0-100:本章整体张力/紧张度。\n"
    f"- scene_type 取其一:{'/'.join(SCENE_TYPES)}。\n"
    "- pov_holder:本章主要视角人物名;is_protagonist_pov:是否主角视角。\n"
    f"- plot_function 取其一:{'/'.join(PLOT_FUNCS)}(铺垫/升级/兑现/反转/喘息)。\n"
    "- hook_type:章末钩子类型(悬念/反转/危机/情感/信息揭示/无 等);cliffhanger_strength 0-100。\n"
    "- summary:一句话概括本章节拍。\n"
    "为给定的每一章各产出一条,chapter_number 必须是给定章节号之一。\n\n"
    "# 输出格式(严格遵守)\n"
    "只输出一个 JSON 对象,形如:\n"
    '{"beats":[{"chapter_number":1,"tension_level":60,"scene_type":"铺垫",'
    '"pov_holder":"主角名","is_protagonist_pov":true,"plot_function":"setup",'
    '"hook_type":"悬念","cliffhanger_strength":50,"summary":"……"}]}\n'
    "不要输出任何解释、Markdown 围栏或多余文本。"
)


def _strip(s: str) -> str:
    return re.sub(r"```json|```", "", s or "").strip()


def _loads(resp) -> dict:
    """返回 {beats:[...]}。兼容:tool_use / {beats:[...]} / 裸数组(strict 偶不包 beats)。"""
    tu = (resp.tool_use or {}).get("input")
    if isinstance(tu, dict) and tu.get("beats"):
        return tu
    try:
        from json_repair import repair_json
        d = json.loads(repair_json(_strip(resp.text)))
    except Exception:
        return {}
    if isinstance(d, dict) and "beats" in d:
        return d
    if isinstance(d, list):                       # 模型返回裸数组
        return {"beats": d}
    if isinstance(d, dict):                        # 单对象
        return {"beats": [d]}
    return {}


def _to_chapter_num(v, fallback: int | None = None) -> int | None:
    """把 chapter_number 容错成整数:支持 1 / "1" / "第 1 章" 等。"""
    if isinstance(v, int):
        return v
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else fallback


def _chapters(head: int = 1100, tail: int = 500) -> list[dict]:
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


def tag_beats(slug: str, *, batch_size: int = 8, max_chapters: int | None = None,
              replace: bool = True) -> dict:
    """对某书逐批抽 chapter_beat。串行(避免 429)。"""
    library.set_active(slug)
    init_schema()  # 含新表 chapter_beat/analysis_card
    chs = _chapters()
    if max_chapters:
        chs = chs[:max_chapters]
    if not chs:
        return {"error": "no chapters — split/extract first", "beats": 0}
    valid = {c["chapter"] for c in chs}
    if replace:
        with session_scope() as s:
            s.execute(delete(M.ChapterBeat))
    total, cost = 0, 0.0
    batches = [chs[i:i + batch_size] for i in range(0, len(chs), batch_size)]
    for bi, batch in enumerate(batches):
        nums = "、".join(str(c["chapter"]) for c in batch)
        body = "\n\n".join(f"【第{c['chapter']}章 {c['title']}】\n{c['text']}" for c in batch)
        try:
            resp = llm.call(agent="analysis.beat", model=MODEL_FAST,
                            system=[{"type": "text", "text": _SYS}],
                            messages=[{"role": "user", "content":
                                       f"为第 {nums} 章逐章判定节拍。\n\n{body}"}],
                            max_tokens=4000, temperature=0.2, response_format=_beat_rf())
            cost += resp.cost_usd or 0.0
            beats = _loads(resp).get("beats") or []
        except Exception as e:  # noqa: BLE001
            print(f"[analysis.beat] batch {bi} 失败: {str(e)[:120]}", flush=True)
            continue
        rows = []
        for bi2, b in enumerate(beats):
            if not isinstance(b, dict):
                continue
            # 容错:chapter_number 可能是 "第 1 章"/字符串;不在本批范围则按位置兜底
            fb = batch[bi2]["chapter"] if bi2 < len(batch) else None
            cn = _to_chapter_num(b.get("chapter_number"), fb)
            if cn not in valid:
                continue
            # 跳过退化空节拍(模型偶发返回缺张力且缺场景的空对象)
            if not b.get("scene_type") and not b.get("tension_level"):
                continue
            rows.append(M.ChapterBeat(
                chapter=int(cn),
                tension_level=int(b.get("tension_level") or 0),
                scene_type=b.get("scene_type"),
                pov_holder=(b.get("pov_holder") or "")[:40],
                is_protagonist_pov=1 if b.get("is_protagonist_pov") else 0,
                plot_function=b.get("plot_function"),
                hook_type=(b.get("hook_type") or "")[:30],
                cliffhanger_strength=int(b.get("cliffhanger_strength") or 0),
                summary=(b.get("summary") or "")[:300],
                created_at=datetime.utcnow()))
        if rows:
            with session_scope() as s:
                for r in rows:  # upsert by PK chapter
                    s.merge(r)
            total += len(rows)
        print(f"[analysis.beat] {slug} batch {bi+1}/{len(batches)} ch{batch[0]['chapter']}-{batch[-1]['chapter']}: +{len(rows)} (累计 {total})", flush=True)
    beat_summary(slug)  # 抽完即聚合 pacing 卡,保持与其它层一致
    return {"beats": total, "batches": len(batches), "cost_usd": round(cost, 4)}


def beat_summary(slug: str) -> dict:
    """聚合:张力曲线 + 场景分布 + 主角POV占比 + 高潮章;落 analysis_card('pacing')。"""
    library.set_active(slug)
    init_schema()
    with session_scope() as s:
        rows = s.execute(select(M.ChapterBeat).order_by(M.ChapterBeat.chapter)).scalars().all()
        if not rows:
            return {"error": "no beats — run tag_beats first"}
        curve = [{"chapter": r.chapter, "tension": r.tension_level,
                  "scene_type": r.scene_type, "is_protagonist_pov": r.is_protagonist_pov,
                  "cliffhanger": r.cliffhanger_strength} for r in rows]
        dist: dict[str, int] = {}
        for r in rows:
            dist[r.scene_type or "其他"] = dist.get(r.scene_type or "其他", 0) + 1
        tens = [r.tension_level or 0 for r in rows]
        big = [r.chapter for r in rows if (r.scene_type == "大高潮") or (r.tension_level or 0) >= 88]
        prot = sum(1 for r in rows if r.is_protagonist_pov)
        card = {
            "n_chapters": len(rows),
            "scene_distribution": dist,
            "tension_avg": round(statistics.mean(tens), 1) if tens else 0,
            "tension_max": max(tens) if tens else 0,
            "protagonist_pov_ratio": round(prot / len(rows), 2),
            "big_climax_chapters": big,
            "avg_cliffhanger": round(statistics.mean([r.cliffhanger_strength or 0 for r in rows]), 1),
        }
        row = s.get(M.AnalysisCard, "pacing")
        if not row:
            row = M.AnalysisCard(category="pacing")
            s.add(row)
        row.card_json = card
        row.updated_at = datetime.utcnow()
    return {"slug": slug, "card": card, "curve": curve}


def get_beats(slug: str) -> dict:
    library.set_active(slug)
    init_schema()
    with session_scope() as s:
        rows = s.execute(select(M.ChapterBeat).order_by(M.ChapterBeat.chapter)).scalars().all()
        card = s.get(M.AnalysisCard, "pacing")
        return {
            "slug": slug,
            "beats": [{"chapter": r.chapter, "tension": r.tension_level, "scene_type": r.scene_type,
                       "pov_holder": r.pov_holder, "is_protagonist_pov": r.is_protagonist_pov,
                       "plot_function": r.plot_function, "hook_type": r.hook_type,
                       "cliffhanger": r.cliffhanger_strength, "summary": r.summary} for r in rows],
            "pacing_card": card.card_json if card else None,
        }
