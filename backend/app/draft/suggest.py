"""润色建议(局部、可采纳、可持久化)—— 不改原文，只产出"哪里该改成什么"的就地替换建议。

落库到 `edit_suggestions`(刷新后仍在 + 审计 + 纳入版本控制)。**锚点失效检测**：
每条建议记 base_hash(生成时中文定稿哈希)；展示/应用时若 quote 在**当前**正文里找不到
(原文被改过)，该条标 stale、禁止应用——避免错位乱改。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select, desc

from ..config import MODEL_STRONG
from ..llm import client as llm
from ..db import session_scope
from ..memory.models import ChapterDraft, EditSuggestion


def _hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]


_SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "edits": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "quote": {"type": "string", "description": "逐字摘自正文、能唯一定位的原文片段(≤40字)"},
                "replacement": {"type": "string", "description": "替换后的文本(直接可用,保持句子通顺)"},
                "category": {"type": "string", "enum": ["套路词", "翻译腔", "时代错置", "文化语域", "其它"]},
                "reason": {"type": "string", "description": "≤40字，为什么要改"},
            },
            "required": ["quote", "replacement", "category", "reason"],
        }},
    },
    "required": ["edits"],
}


def _loads(t: str) -> dict:
    t = re.sub(r"```json|```", "", t or "").strip()
    try:
        return json.loads(t)
    except Exception:
        try:
            from json_repair import repair_json
            d = json.loads(repair_json(t))
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}


def _row_view(r: EditSuggestion, current_text: str, base_hash: str) -> dict[str, Any]:
    """把一条建议渲染成前端视图，附**实时**锚点状态(对照当前正文)。"""
    cnt = current_text.count(r.quote) if r.quote else 0
    # 可应用 = 还没应用/拒绝 + 在当前正文里能唯一(或至少存在)定位到
    applicable = r.status in ("pending", "accepted") and cnt >= 1
    stale = r.status in ("pending", "accepted") and cnt == 0  # 原文已变、锚点失效
    return {
        "id": r.id, "quote": r.quote, "replacement": r.replacement,
        "category": r.category, "reason": r.reason, "status": r.status,
        "found": cnt >= 1, "count": cnt, "applicable": applicable, "stale": stale,
        "ambiguous": cnt > 1,
        "base_changed": (base_hash != r.base_hash),
    }


def list_suggestions(draft_id: int) -> dict[str, Any]:
    """读最近一批建议 + **实时**重算锚点状态(对照当前中文定稿)。"""
    with session_scope() as s:
        d = s.get(ChapterDraft, draft_id)
        if not d:
            return {"draft_id": draft_id, "edits": [], "note": "无草稿"}
        current = d.final_text or ""
        cur_hash = _hash(current)
        latest = s.execute(select(EditSuggestion).where(
            EditSuggestion.draft_id == draft_id,
            EditSuggestion.status.notin_(("superseded",))
        ).order_by(desc(EditSuggestion.id))).scalars().all()
        # 只取最新 batch
        if not latest:
            return {"draft_id": draft_id, "chapter_index": d.chapter_index, "edits": [], "base_changed": False}
        batch = latest[0].batch_id
        rows = [r for r in latest if r.batch_id == batch]
        rows.sort(key=lambda r: r.id)
        edits = [_row_view(r, current, cur_hash) for r in rows]
        base_changed = any(e["base_changed"] for e in edits)
        return {"draft_id": draft_id, "chapter_index": d.chapter_index,
                "batch_id": batch, "base_changed": base_changed, "edits": edits}


def suggest_edits(draft_id: int) -> dict[str, Any]:
    """扫描某章中文定稿，产出就地替换建议并**落库**(新批次；旧 pending 标 superseded)。"""
    with session_scope() as s:
        d = s.get(ChapterDraft, draft_id)
        if not d or not (d.final_text or "").strip():
            return {"draft_id": draft_id, "edits": [], "note": "无正文"}
        prose = d.final_text
        chapter_index = d.chapter_index
    base_hash = _hash(prose)

    pitfalls, card = [], None
    try:
        from ..style.pipeline import get_profile
        p = get_profile() or {}
        pitfalls = ((p.get("profile") or {}).get("pitfalls_to_avoid")) or []
        card = p.get("register_card")
    except Exception:  # noqa: BLE001
        pass

    sys = (
        "你是中文小说润色建议员。扫描本章正文，挑出**应当就地替换**的问题点，"
        "每条给出能在原文唯一定位的 quote + 替换文本 replacement + 类别 + 理由。\n"
        "重点找四类：\n"
        "① 套路词/口水反应词(瞳孔骤然收缩、呼吸一滞、后颈一凉、心头一震、倒吸一口凉气…)；\n"
        "② 翻译腔/空话(似乎、某种、一种说不清的感觉、仿佛有什么…这类落不到实处的抽象)；\n"
        "③ 时代错置(与世界观语域卡的技术/年代基准不符的现代物/词/网络语)；\n"
        "④ 文化语域错置(按词的**归属角色**判：跨文化错置才报，属于该阵营文化的词不报)。\n"
        + (f"\n# 避用词(pitfalls)\n{json.dumps(pitfalls, ensure_ascii=False)}" if pitfalls else "")
        + (f"\n# 世界观语域卡\n{json.dumps(card, ensure_ascii=False)}" if card else "")
        + "\n\n# 纪律\n只挑**确有把握**的(宁缺毋滥，不要为改而改、不要改情节)；replacement 要保持上下文通顺、"
        "符合该角色文化与时代；quote 必须逐字摘自正文且尽量短而唯一。\n"
        "# 输出格式(严格)\n只输出一个 JSON 对象，无其它文字、无 markdown 围栏，符合此 schema：\n"
        + json.dumps(_SUGGEST_SCHEMA, ensure_ascii=False)
    )
    resp = llm.call(agent="draft.suggest_edits", model=MODEL_STRONG, system=sys,
                    messages=[{"role": "user", "content": f"# 第{chapter_index}章正文\n\n{prose}"}],
                    max_tokens=8000, temperature=0.3)
    out = _loads(resp.text or "")

    batch_id = f"{draft_id}-{base_hash}-{_hash(resp.text or '')[:6]}"
    with session_scope() as s:
        # 旧的未应用建议标 superseded（保留 applied 作审计）
        for r in s.execute(select(EditSuggestion).where(
                EditSuggestion.draft_id == draft_id,
                EditSuggestion.status.in_(("pending", "accepted", "stale")))).scalars().all():
            r.status = "superseded"; r.updated_at = datetime.utcnow()
        for e in out.get("edits") or []:
            q = str(e.get("quote", "")).strip(); r = str(e.get("replacement", "")).strip()
            if not q or not r:
                continue
            s.add(EditSuggestion(
                draft_id=draft_id, chapter_index=chapter_index, batch_id=batch_id,
                base_hash=base_hash, quote=q, replacement=r,
                category=e.get("category", "其它"), reason=str(e.get("reason", ""))[:60],
                status="pending"))

    # 纳入版本控制：把这批建议 dump 成 suggestions/chN.json（随下次 commit 进 git）
    try:
        from ..repo import store as _repo
        _repo.dump_suggestions(chapter_index, list_suggestions(draft_id).get("edits") or [])
    except Exception:  # noqa: BLE001
        pass

    res = list_suggestions(draft_id)
    res["cost_usd"] = resp.cost_usd
    return res


def apply_edits(draft_id: int, accepted_ids: list[int]) -> dict[str, Any]:
    """把用户采纳的建议(按 id)就地替换进中文定稿。**应用时再校验锚点**：
    若 quote 在当前正文里找不到(原文已变/被前一条改动覆盖)→ 该条标 stale、计入 failed，
    绝不错位乱改。其余正常 applied。最后落库 + 导出 manuscript + git commit。
    """
    ids = set(int(x) for x in (accepted_ids or []))
    applied, failed = [], []
    with session_scope() as s:
        d = s.get(ChapterDraft, draft_id)
        if not d or not (d.final_text or "").strip():
            return {"ok": False, "note": "无正文"}
        text = d.final_text
        chapter_index = d.chapter_index
        rows = s.execute(select(EditSuggestion).where(EditSuggestion.id.in_(ids))).scalars().all() if ids else []
        # 按 id 顺序应用，保证可复现
        for r in sorted(rows, key=lambda x: x.id):
            if r.quote and r.quote in text:
                text = text.replace(r.quote, r.replacement, 1)  # 只替第一次出现
                r.status = "applied"; r.updated_at = datetime.utcnow()
                applied.append({"id": r.id, "quote": r.quote})
            else:
                r.status = "stale"; r.updated_at = datetime.utcnow()
                failed.append({"id": r.id, "quote": r.quote, "reason": "锚点失效（原文已更改）"})
        d.final_text = text
        d.updated_at = datetime.utcnow()

    repo_note = None
    try:
        from ..repo import store as _repo
        _repo.dump_manuscript(chapter_index)
        _repo.dump_suggestions(chapter_index, list_suggestions(draft_id).get("edits") or [])
        rr = _repo.commit(f"ch{chapter_index}: 采纳 {len(applied)} 处润色建议")
        repo_note = "committed" if rr.get("ok") else "nochange"
    except Exception as e:  # noqa: BLE001
        repo_note = f"repo_failed:{str(e)[:60]}"

    return {"ok": True, "applied": len(applied), "failed": failed,
            "repo": repo_note, "en_stale": bool(applied)}
