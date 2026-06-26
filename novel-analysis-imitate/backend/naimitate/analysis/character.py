"""主要人物简介卡:从已有信号判定重要人物 → MODEL_STRONG 生成简介。

重要度信号(无需基础实体抽取):
- 关系度数:在 relationship_event 中作为 a/b 出现的次数;
- POV 出场:在 chapter_beat 作为 pov_holder 的章数;
- 提及频次:在 beat summary 文本中被点名的次数。
综合排序取 top N,逐人让模型据其关系事件 + 出场节拍写简介卡。全程 book_scope。
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from sqlalchemy import select, delete  # noqa: E402
from app.config import MODEL_STRONG  # noqa: E402
from app.db import session_scope, book_scope  # noqa: E402
from app.llm import client as llm  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402
from . import models as M  # noqa: E402


def _strip(s: str) -> str:
    return re.sub(r"```json|```", "", s or "").strip()


def _loads(resp) -> dict:
    try:
        from json_repair import repair_json
        d = json.loads(repair_json(_strip(resp.text)))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _rank(slug: str, top_n: int) -> list[tuple[str, dict]]:
    """返回 [(name, signals)] 按综合分降序。"""
    with session_scope() as s:
        rels = s.execute(select(M.RelationshipEvent)).scalars().all()
        beats = s.execute(select(M.ChapterBeat)).scalars().all()
    deg = Counter()
    rel_with: dict[str, Counter] = {}
    first_ch: dict[str, int] = {}
    for r in rels:
        for who, other in ((r.a, r.b), (r.b, r.a)):
            if not who:
                continue
            deg[who] += 1
            rel_with.setdefault(who, Counter())[f"{other}:{r.state}"] += 1
            first_ch[who] = min(first_ch.get(who, 10 ** 9), r.chapter or 10 ** 9)
    pov = Counter()
    for b in beats:
        if b.pov_holder:
            pov[b.pov_holder] += 1
    # 提及频次:beat summary 里点名(只统计已知候选名,避免分词)
    cand = set(deg) | set(pov)
    mention = Counter()
    blob = "\n".join(b.summary or "" for b in beats)
    for name in cand:
        if len(name) >= 2:
            mention[name] = blob.count(name)
    scored = []
    for name in cand:
        score = deg[name] * 3 + pov[name] * 2 + min(mention[name], 40)
        scored.append((name, {"score": score, "deg": deg[name], "pov": pov[name],
                              "mention": mention[name],
                              "relations": [k for k, _ in rel_with.get(name, Counter()).most_common(8)],
                              "first_chapter": first_ch.get(name, 0) if first_ch.get(name, 0) < 10 ** 9 else 0}))
    scored.sort(key=lambda x: -x[1]["score"])
    return scored[:top_n]


_SYS = (
    "你是中文小说的『人物档案员』。根据给定人物的关系事件 + 出场信息,写一张简介卡。\n"
    "输出 JSON:{role(主角/配角/反派/导师/盟友/对手等), importance(0-100), one_line(一句话定位), "
    "description(2-3句简介:身份/在故事中的作用), personality(性格与核心动机), "
    "arc(人物弧光,『从…到…』一句), key_relations([{who, relation}] 最多5条)}。\n"
    "只依据给定信息,不要杜撰。只输出 JSON 对象。"
)


def build_cards(slug: str, *, top_n: int = 12) -> dict:
    with book_scope(slug):
        init_schema()
        ranked = _rank(slug, top_n)
        if not ranked:
            return {"error": "无关系/节拍数据 — 先跑节拍+关系层", "characters": 0}
        # 取每人出场节拍摘要(其作为 POV 或被提及的若干章)
        with session_scope() as s:
            beats = s.execute(select(M.ChapterBeat).order_by(M.ChapterBeat.chapter)).scalars().all()
            rels = s.execute(select(M.RelationshipEvent)).scalars().all()
        n = 0
        with session_scope() as s:
            s.execute(delete(M.CharacterCard))
        for name, sig in ranked:
            ctx_beats = [f"第{b.chapter}章 {b.summary}" for b in beats
                         if b.pov_holder == name or (b.summary and name in b.summary)][:14]
            ctx_rels = [f"第{r.chapter}章 与{r.b if r.a==name else r.a}: {r.state}({r.trigger or ''})"
                        for r in rels if name in (r.a, r.b)][:12]
            user = (f"人物:{name}\n关系度数{sig['deg']} POV出场{sig['pov']}章 提及{sig['mention']}次\n\n"
                    f"# 关系事件\n" + "\n".join(ctx_rels) + "\n\n# 出场节拍\n" + "\n".join(ctx_beats))
            try:
                resp = llm.call(agent="analysis.worldview", model=MODEL_STRONG,
                                system=[{"type": "text", "text": _SYS}],
                                messages=[{"role": "user", "content": user[:30000]}],
                                max_tokens=1500, temperature=0.4, response_format={"type": "json_object"})
                d = _loads(resp)
            except Exception as e:  # noqa: BLE001
                print(f"[character] {name} 失败: {str(e)[:90]}", flush=True)
                continue
            with session_scope() as s:
                s.add(M.CharacterCard(
                    name=name[:40], role=(d.get("role") or "")[:20],
                    importance=max(0, min(100, int(d.get("importance") or sig["score"]))),
                    one_line=(d.get("one_line") or "")[:120],
                    description=(d.get("description") or "")[:600],
                    personality=(d.get("personality") or "")[:400],
                    arc=(d.get("arc") or "")[:300],
                    key_relations_json=d.get("key_relations") or [],
                    first_chapter=sig["first_chapter"], created_at=datetime.utcnow()))
            n += 1
            print(f"[character] {slug} {name} 卡完成 ({n}/{len(ranked)})", flush=True)
        return {"characters": n}


def get_cards(slug: str) -> dict:
    with book_scope(slug):
        init_schema()
        with session_scope() as s:
            rows = s.execute(select(M.CharacterCard).order_by(M.CharacterCard.importance.desc())).scalars().all()
            return {"slug": slug, "characters": [{
                "name": r.name, "role": r.role, "importance": r.importance,
                "one_line": r.one_line, "description": r.description, "personality": r.personality,
                "arc": r.arc, "key_relations": r.key_relations_json or [], "first_chapter": r.first_chapter,
            } for r in rows]}
