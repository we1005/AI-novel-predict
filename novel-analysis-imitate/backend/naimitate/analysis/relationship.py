"""Phase 1 · relationship_event 分析层:人物关系演变的时间序列。

现有 backend 的 relationships 表是『关系快照』,缺『何时因何事从 A 态变到 B 态』。
本层逐批扫原文,抽出关系状态的**转变事件**,聚合出每对关系的演变轨迹。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from collections import defaultdict

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from sqlalchemy import select, text as _sql_text, delete  # noqa: E402
from app.config import MODEL_FAST  # noqa: E402
from app.db import get_engine, session_scope  # noqa: E402
from app.books import library  # noqa: E402
from app.llm import client as llm  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402
from . import models as M  # noqa: E402

STATES = ["萍水", "结盟", "恋人", "反目", "背叛", "忠贞", "宿敌", "师徒", "亲情", "竞争", "其他"]

_ITEM = {
    "type": "object",
    "properties": {
        "chapter_number": {"type": "integer"},
        "a": {"type": "string"},
        "b": {"type": "string"},
        "state": {"type": "string", "enum": STATES},
        "trigger": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["chapter_number", "a", "b", "state", "trigger", "summary"],
    "additionalProperties": False,
}
_SCHEMA = {"type": "object", "properties": {"events": {"type": "array", "items": _ITEM}},
           "required": ["events"], "additionalProperties": False}


def _rf() -> dict:
    return {"type": "json_schema",
            "json_schema": {"name": "relationship_events", "strict": True, "schema": _SCHEMA}}


_SYS = (
    "你是中文小说的『人物关系分析师』。给你若干章原文,找出本批次中**人物关系发生明确转变**的事件。\n"
    "只记关系状态真正变化的瞬间(如结盟→反目、萍水→恋人),不记日常互动。一批可能 0 条或多条。\n"
    "- a、b:关系双方人物名(用全书统一称呼)。\n"
    f"- state 取其一:{'/'.join(STATES)}(转变后的新关系态)。\n"
    "- trigger:导致此转变的具体事件(简述)。\n"
    "- summary:一句话概括。\n"
    "chapter_number 必须是给定章节号之一。"
)


def _strip(s: str) -> str:
    return re.sub(r"```json|```", "", s or "").strip()


def _loads(resp) -> list:
    tu = (resp.tool_use or {}).get("input")
    if isinstance(tu, dict) and isinstance(tu.get("events"), list):
        return tu["events"]
    try:
        from json_repair import repair_json
        d = json.loads(repair_json(_strip(resp.text)))
    except Exception:
        return []
    if isinstance(d, dict) and isinstance(d.get("events"), list):
        return d["events"]
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


def tag_events(slug: str, *, batch_size: int = 6, max_chapters: int | None = None,
               replace: bool = True) -> dict:
    library.set_active(slug)
    init_schema()
    chs = _chapters()
    if max_chapters:
        chs = chs[:max_chapters]
    if not chs:
        return {"error": "no chapters", "events": 0}
    valid = {c["chapter"] for c in chs}
    if replace:
        with session_scope() as s:
            s.execute(delete(M.RelationshipEvent))
    total, cost = 0, 0.0
    batches = [chs[i:i + batch_size] for i in range(0, len(chs), batch_size)]
    for bi, batch in enumerate(batches):
        nums = "、".join(str(c["chapter"]) for c in batch)
        body = "\n\n".join(f"【第{c['chapter']}章 {c['title']}】\n{c['text']}" for c in batch)
        try:
            resp = llm.call(agent="analysis.relationship", model=MODEL_FAST,
                            system=[{"type": "text", "text": _SYS
                                     + "\n\n# 输出格式\n只输出 JSON 对象 {\"events\":[...]}。无转变则空数组。"}],
                            messages=[{"role": "user", "content":
                                       f"分析第 {nums} 章的关系演变。\n\n{body}"}],
                            max_tokens=4000, temperature=0.2, response_format=_rf())
            cost += resp.cost_usd or 0.0
            events = _loads(resp)
        except Exception as e:  # noqa: BLE001
            print(f"[analysis.relationship] batch {bi} 失败: {str(e)[:120]}", flush=True)
            continue
        rows = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            cn = _to_num(ev.get("chapter_number"), batch[0]["chapter"])
            a, b = (ev.get("a") or "").strip(), (ev.get("b") or "").strip()
            if cn not in valid or not a or not b:
                continue
            st = ev.get("state")
            rows.append(M.RelationshipEvent(
                chapter=int(cn), a=a[:40], b=b[:40],
                state=st if st in STATES else "其他",
                trigger=(ev.get("trigger") or "")[:200],
                summary=(ev.get("summary") or "")[:300],
                created_at=datetime.utcnow()))
        if rows:
            with session_scope() as s:
                for r in rows:
                    s.add(r)
            total += len(rows)
        print(f"[analysis.relationship] {slug} batch {bi+1}/{len(batches)} "
              f"ch{batch[0]['chapter']}-{batch[-1]['chapter']}: +{len(rows)} (累计 {total})", flush=True)
    summarize(slug)
    return {"events": total, "batches": len(batches), "cost_usd": round(cost, 4)}


def _pair_key(a: str, b: str) -> str:
    return " — ".join(sorted([a, b]))


def summarize(slug: str) -> dict:
    library.set_active(slug)
    init_schema()
    with session_scope() as s:
        rows = s.execute(select(M.RelationshipEvent).order_by(M.RelationshipEvent.chapter)).scalars().all()
        if not rows:
            return {"error": "no events"}
        tracks: dict[str, list] = defaultdict(list)
        for r in rows:
            tracks[_pair_key(r.a, r.b)].append({"chapter": r.chapter, "state": r.state})
        # 反转次数(从某态变到对立态)粗略衡量关系戏剧性
        card = {
            "n_events": len(rows),
            "n_pairs": len(tracks),
            "most_dynamic_pairs": sorted(
                ({"pair": k, "changes": len(v)} for k, v in tracks.items()),
                key=lambda x: -x["changes"])[:10],
        }
        row = s.get(M.AnalysisCard, "relationship")
        if not row:
            row = M.AnalysisCard(category="relationship")
            s.add(row)
        row.card_json = card
        row.updated_at = datetime.utcnow()
    return {"slug": slug, "card": card}


def get_events(slug: str) -> dict:
    library.set_active(slug)
    init_schema()
    with session_scope() as s:
        rows = s.execute(select(M.RelationshipEvent).order_by(M.RelationshipEvent.chapter)).scalars().all()
        card = s.get(M.AnalysisCard, "relationship")
        tracks: dict[str, list] = defaultdict(list)
        for r in rows:
            tracks[_pair_key(r.a, r.b)].append(
                {"chapter": r.chapter, "state": r.state, "trigger": r.trigger})
        return {
            "slug": slug,
            "events": [{"chapter": r.chapter, "a": r.a, "b": r.b, "state": r.state,
                        "trigger": r.trigger, "summary": r.summary} for r in rows],
            "tracks": tracks,
            "relationship_card": card.card_json if card else None,
        }
