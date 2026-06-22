"""Entity de-duplication.

Parallel, per-batch extraction over a long book repeatedly re-introduces the
same entity under slightly different names (e.g. 西泽尔 vs 西泽尔·博尔吉亚,
Longinus vs 圣枪装具·Longinus). On multi-POV / non-linear books this is severe
and fragments the graph (split importance, split relationships, duplicate item
cards). This pass finds same-entity duplicates and merges them.

Strategy: cheap candidate generation (same type + name overlap / shared alias)
→ one LLM judge call (code model, clean JSON) to confirm true duplicates and
pick the canonical name → merge (reassign all FKs, fold aliases, sum importance).
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select

from ..config import MODEL_STRONG
from ..db import session_scope
from ..llm import client as llm
from ..memory.models import Entity, EntityState, PlotPoint, Foreshadowing, Relationship


def _norm(name) -> str:
    if not isinstance(name, str):
        name = "" if name is None else str(name)
    return re.sub(r"[\s·.,\-—_、]", "", name).lower()


def _alias_strs(v) -> list[str]:
    """Coerce an entity's aliases_json (any shape the extractor produced) into a
    clean list of strings. Extraction models occasionally emit a list-of-dict or
    a dict instead of a list-of-str (e.g. entity 蜘蛛切 got a metadata object) —
    pull a usable name out and drop the rest so dedup never crashes on it."""
    out: list[str] = []
    if v is None:
        return out
    items = v if isinstance(v, list) else [v]
    for x in items:
        if isinstance(x, str):
            if x.strip():
                out.append(x)
        elif isinstance(x, dict):
            for k in ("name", "alias", "title", "value"):
                if isinstance(x.get(k), str) and x[k].strip():
                    out.append(x[k]); break
        # ignore other types
    return out


def _candidates() -> list[dict]:
    """Same-type pairs that look like they might be the same entity."""
    with session_scope() as s:
        rows = s.execute(select(Entity)).scalars().all()
        ents = [{"id": e.id, "type": e.type, "name": e.name,
                 "aliases": _alias_strs(e.aliases_json), "importance": e.importance or 0,
                 "desc": (e.description or "")[:80]} for e in rows]

    by_type: dict[str, list[dict]] = {}
    for e in ents:
        by_type.setdefault(e["type"], []).append(e)

    pairs: list[dict] = []
    for typ, group in by_type.items():
        for i in range(len(group)):
            for jdx in range(i + 1, len(group)):
                a, b = group[i], group[jdx]
                na, nb = _norm(a["name"]), _norm(b["name"])
                if not na or not nb:
                    continue
                aliases = {_norm(x) for x in (a["aliases"] + b["aliases"])}
                overlap = (
                    na in nb or nb in na                       # substring
                    or na in aliases or nb in aliases          # alias hit
                )
                if overlap:
                    pairs.append({"a": a, "b": b})
    return pairs


_JUDGE_TOOL = {
    "name": "report_duplicates",
    "description": "Decide which candidate entity pairs are the SAME entity and should be merged.",
    "input_schema": {
        "type": "object",
        "properties": {
            "merges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "keep_id": {"type": "integer", "description": "规范实体的 id（保留）"},
                        "merge_id": {"type": "integer", "description": "被合并掉的重复实体 id"},
                        "canonical_name": {"type": "string", "description": "合并后使用的规范名称"},
                    },
                    "required": ["keep_id", "merge_id", "canonical_name"],
                },
            }
        },
        "required": ["merges"],
    },
}

_JUDGE_SYSTEM = """你在给一部小说的实体去重。给你若干"候选对"，每对是名字有重叠的同类实体。判断**哪些对其实是同一个实体**（应合并），哪些不是。

判定原则：
- 同一实体：全名 vs 简称（西泽尔 / 西泽尔·博尔吉亚）、含修饰的同物（Longinus / 圣枪装具·Longinus）、音译变体、带头衔同人（教皇 / 教皇xx）。
- 不是同一实体（绝不合并）：父子/家族不同成员（西泽尔 / 西泽尔的母亲）、同姓不同人、同系列不同物、泛称 vs 具体。
- 拿不准就**不合并**（宁缺毋滥）。

对每个确认的重复对，输出 keep_id（保留信息更全/更重要的那个，通常 importance 高的）、merge_id、canonical_name（合并后用哪个名字，一般用更完整或更常用的）。调用 report_duplicates。"""


def _judge(pairs: list[dict]) -> list[dict]:
    if not pairs:
        return []
    lines = []
    for p in pairs:
        a, b = p["a"], p["b"]
        lines.append(
            f"- 类型[{a['type']}] | A: id={a['id']} 名='{a['name']}' 别名={a['aliases']} 重要度={a['importance']} 简介='{a['desc']}'"
            f" || B: id={b['id']} 名='{b['name']}' 别名={b['aliases']} 重要度={b['importance']} 简介='{b['desc']}'"
        )
    user = "候选对：\n" + "\n".join(lines) + "\n\n判断哪些是同一实体并调用 report_duplicates。"
    resp = llm.call(
        agent="graph.dedup", model=MODEL_STRONG, system=_JUDGE_SYSTEM,
        messages=[{"role": "user", "content": user}],
        tools=[_JUDGE_TOOL], tool_choice={"type": "tool", "name": _JUDGE_TOOL["name"]},
        max_tokens=4000, temperature=0.1,
    )
    out = (resp.tool_use or {}).get("input") or {}
    if isinstance(out, dict) and set(out.keys()) <= {"_raw"}:
        try:
            from json_repair import repair_json
            out = json.loads(repair_json(out.get("_raw", "")))
        except Exception:
            out = {}
    return [m for m in (out.get("merges") or []) if isinstance(m, dict) and m.get("keep_id") and m.get("merge_id")]


def _merge_one(s, keep_id: int, merge_id: int, canonical_name: str | None) -> bool:
    keep = s.get(Entity, keep_id)
    dup = s.get(Entity, merge_id)
    if not keep or not dup or keep_id == merge_id or keep.type != dup.type:
        return False

    # Collect alias/importance/chapter before deleting the dup.
    aliases = set(keep.aliases_json or []) | set(dup.aliases_json or [])
    aliases.add(dup.name)
    if keep.name:
        aliases.add(keep.name)
    new_importance = (keep.importance or 0) + (dup.importance or 0)
    new_first = keep.first_appear_chapter
    if dup.first_appear_chapter and (not new_first or dup.first_appear_chapter < new_first):
        new_first = dup.first_appear_chapter

    # Reassign FKs from dup → keep.
    for st in s.execute(select(EntityState).where(EntityState.entity_id == merge_id)).scalars():
        st.entity_id = keep_id
    for pp in s.execute(select(PlotPoint)).scalars():
        ids = pp.involved_entity_ids_json or []
        if merge_id in ids:
            pp.involved_entity_ids_json = sorted({keep_id if x == merge_id else x for x in ids})
    for fs in s.execute(select(Foreshadowing)).scalars():
        ids = fs.related_entity_ids_json or []
        if merge_id in ids:
            fs.related_entity_ids_json = sorted({keep_id if x == merge_id else x for x in ids})
    for rel in s.execute(select(Relationship)).scalars():
        if rel.from_entity_id == merge_id:
            rel.from_entity_id = keep_id
        if rel.to_entity_id == merge_id:
            rel.to_entity_id = keep_id

    # Delete the dup FIRST and flush, so its (type, name) slot is freed before
    # we (possibly) rename keep to that same name — avoids the UNIQUE collision.
    s.delete(dup)
    s.flush()

    # Choose final name: canonical only if no OTHER entity already holds it.
    final_name = keep.name
    if canonical_name and canonical_name != keep.name:
        clash = s.execute(
            select(Entity).where(Entity.type == keep.type, Entity.name == canonical_name,
                                 Entity.id != keep_id).limit(1)
        ).scalar_one_or_none()
        if clash is None:
            final_name = canonical_name
    keep.name = final_name
    keep.importance = new_importance
    keep.first_appear_chapter = new_first
    keep.aliases_json = sorted(a for a in aliases if a and a != final_name)
    s.flush()
    return True


def run() -> dict[str, Any]:
    pairs = _candidates()
    merges = _judge(pairs)
    done = 0
    errors = 0
    redirect: dict[int, int] = {}   # chain resolution across separate txns

    def resolve(i: int) -> int:
        while i in redirect:
            i = redirect[i]
        return i

    # One transaction per merge so a single bad pair can't roll back the rest.
    for m in merges:
        keep = resolve(int(m["keep_id"]))
        mid = resolve(int(m["merge_id"]))
        if keep == mid:
            continue
        try:
            with session_scope() as s:
                ok = _merge_one(s, keep, mid, m.get("canonical_name"))
            if ok:
                redirect[mid] = keep
                done += 1
        except Exception:
            errors += 1

    # Drop self-loop / duplicate relationships created by merges.
    with session_scope() as s:
        seen = set()
        for rel in s.execute(select(Relationship)).scalars():
            key = (rel.from_entity_id, rel.to_entity_id, rel.label)
            if rel.from_entity_id == rel.to_entity_id or key in seen:
                s.delete(rel)
            else:
                seen.add(key)

    return {"candidates": len(pairs), "confirmed": len(merges), "merged": done, "errors": errors}
