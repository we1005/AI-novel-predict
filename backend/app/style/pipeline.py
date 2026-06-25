"""Author writing-style analysis pipeline (opt-in, per book).

Samples chapters across the book, runs one strong-model analysis pass, and
stores a single StyleProfile row per book. Downstream continuation reads the
profile (when mimic_enabled) to imitate the original author's voice instead of
the default punchy-网文 voice.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select, text as _sql_text

from ..config import MODEL_STRONG
from ..db import get_engine, session_scope
from ..llm import client as llm
from ..llm.prompts.style import STYLE_ANALYZE_SYSTEM, STYLE_TOOL, build_style_user_message
from ..memory.models import StyleProfile

# Reuse the corpus-junk stripper so scraper footers don't pollute analysis.
_JUNK = ("【全书完】", "全书完", "（全文完）", "全文完", "书香门第",
         "本作品来自互联网", "版权归作者", "本书由", "txt下载", "TXT下载")


def _clean(t: str, cap: int = 4000) -> str:
    t = (t or "").strip()
    for mk in _JUNK:
        i = t.find(mk)
        if i != -1:
            t = t[:i]
    t = t.strip()
    return t[:cap]


def _sample_chapters(n: int = 8, per_chars: int = 3500) -> list[dict]:
    """Pick ~n chapters spread across the book (full text from chapter_fts)."""
    with get_engine().begin() as conn:
        rows = conn.execute(
            _sql_text("SELECT chapter, title, body FROM chapter_fts "
                      "WHERE body IS NOT NULL AND chapter IS NOT NULL ORDER BY chapter")
        ).mappings().all()
    chapters = [r for r in rows if (r.get("body") or "").strip()]
    if not chapters:
        return []
    total = len(chapters)
    n = min(n, total)
    # Evenly spaced picks across the book (skip the very first chapter — often
    # a prologue with atypical voice).
    if total <= n:
        idxs = list(range(total))
    else:
        idxs = [round(i * (total - 1) / (n - 1)) for i in range(n)] if n > 1 else [total // 2]
    out: list[dict] = []
    seen = set()
    for i in idxs:
        if i in seen:
            continue
        seen.add(i)
        r = chapters[i]
        out.append({"chapter": r["chapter"], "title": r.get("title") or "",
                    "text": _clean(r.get("body") or "", per_chars)})
    return out


def analyze(sample_n: int = 8) -> dict[str, Any]:
    """Run style analysis on sampled chapters; upsert the book's StyleProfile."""
    samples = _sample_chapters(sample_n)
    if not samples:
        raise RuntimeError("no chapters to analyze — split + ingest the book first")

    # JSON-in-text, not forced tool_choice: doubao-code silently returns
    # finish=tool_calls with empty output on this big nested style schema
    # (esp. long-chapter books like 龙族) — same failure as predict/arc (改进记录
    # #14). Embed the schema; the _loads(resp.text) fallback below parses it.
    _style_hint = (
        "\n\n# 输出格式（严格 · 覆盖前述任何「调用工具」指示）\n"
        "只输出一个 JSON 对象，不要任何其它文字、不要 markdown 围栏。必须严格符合此 JSON Schema：\n"
        + json.dumps(STYLE_TOOL["input_schema"], ensure_ascii=False)
    )
    resp = llm.call(
        agent="style.analyze",
        model=MODEL_STRONG,
        system=STYLE_ANALYZE_SYSTEM + _style_hint,
        messages=[{"role": "user", "content": build_style_user_message(samples)}],
        max_tokens=8000,
        temperature=0.3,
        response_format="json_object",   # 火山模型试点:强制合法 JSON(消除围栏/markdown)
    )
    def _loads(s: str) -> dict:
        s = re.sub(r"```json|```", "", s or "").strip()
        try:
            return json.loads(s)
        except Exception:
            try:
                from json_repair import repair_json
                d = json.loads(repair_json(s))
                return d if isinstance(d, dict) else {}
            except Exception:
                return {}

    profile = (resp.tool_use or {}).get("input") or {}
    # Some models (e.g. minimax-m3) return malformed/truncated tool-arg JSON,
    # which client.py surfaces as {"_raw": "..."}; repair it.
    if isinstance(profile, dict) and set(profile.keys()) <= {"_raw"}:
        profile = _loads(profile.get("_raw", ""))
    if not profile and resp.text:
        profile = _loads(resp.text)
    if not isinstance(profile, dict):
        profile = {}

    summary = profile.get("overall_voice", "")[:400]
    is_western = bool(profile.get("is_western_setting"))
    sampled = [s["chapter"] for s in samples]

    with session_scope() as s:
        row = s.execute(select(StyleProfile).limit(1)).scalar_one_or_none()
        if row is None:
            row = StyleProfile()
            s.add(row)
        row.profile_json = profile
        row.summary = summary
        row.sampled_chapters = sampled
        row.model = resp.raw.model if hasattr(resp.raw, "model") else MODEL_STRONG
        row.cost_usd = resp.cost_usd
        row.updated_at = datetime.utcnow()
        # Default bilingual ON for western-setting books (user can still toggle).
        if row.bilingual is None:
            row.bilingual = 1 if is_western else 0

    return get_profile()


def extract_scene_exemplars(sample_n: int = 6) -> dict[str, Any]:
    """从原著采样章节里抽取**各场景类型的真实范例段落**（verbatim），存进
    style_profile.scene_exemplars_json。写作时按本章场景类型注入同类范文当 few-shot，
    让 writer 照着原作语感写——比只给"分场景笔法"的文字描述有效得多。
    """
    samples = _sample_chapters(sample_n, per_chars=5000)
    if not samples:
        raise RuntimeError("no chapters — split + ingest first")
    corpus_text = "\n\n".join(f"【第{s['chapter']}章片段】\n{s['text']}" for s in samples)
    schema = {"type": "object", "properties": {k: {"type": "array", "items": {"type": "string"}}
              for k in ("combat", "dialogue", "scenery", "psychology")}}
    sys = (
        "你在为'模仿原作者文风'挑选范文。从下面原著片段中，为每个场景类型各摘出 1-2 段"
        "**最能代表该作者笔法的连续原文**（逐字摘录，每段 150-400 字，不要改写、不要拼接）：\n"
        "- combat 打斗/动作场面\n- dialogue 对话场面\n- scenery 景物/环境描写\n- psychology 心理/情绪刻画\n"
        "找不到某类就给空数组。只输出 JSON，键为上述四类，值为原文段落字符串数组。\n"
        "# 输出格式（严格）\n只输出一个 JSON 对象，无其它文字、无 markdown 围栏，符合此 schema：\n"
        + json.dumps(schema, ensure_ascii=False)
    )
    resp = llm.call(agent="style.exemplars", model=MODEL_STRONG, system=sys,
                    messages=[{"role": "user", "content": corpus_text}],
                    max_tokens=8000, temperature=0.2)
    def _loads(t: str) -> dict:
        t = re.sub(r"```json|```", "", t or "").strip()
        try:
            return json.loads(t)
        except Exception:
            try:
                from json_repair import repair_json
                d = json.loads(repair_json(t)); return d if isinstance(d, dict) else {}
            except Exception:
                return {}
    ex = _loads(resp.text or "")
    # 规整：每类最多 2 段、每段截到 500 字
    clean = {}
    for k in ("combat", "dialogue", "scenery", "psychology"):
        vals = ex.get(k) or []
        if isinstance(vals, str):
            vals = [vals]
        clean[k] = [str(v).strip()[:500] for v in vals if str(v).strip()][:2]
    with session_scope() as s:
        row = s.execute(select(StyleProfile).limit(1)).scalar_one_or_none()
        if row is None:
            row = StyleProfile(); s.add(row)
        row.scene_exemplars_json = clean
        row.updated_at = datetime.utcnow()
    return {"counts": {k: len(v) for k, v in clean.items()}, "cost_usd": resp.cost_usd}


def extract_register_card(sample_n: int = 8) -> dict[str, Any]:
    """抽取「世界观语域卡」：技术/年代基准 + 各阵营文化语域，供「时代语域」第4审逐元素判定。
    存进 style_profile.register_card_json。"""
    samples = _sample_chapters(sample_n, per_chars=4000)
    if not samples:
        raise RuntimeError("no chapters — split + ingest first")
    corpus_text = "\n\n".join(f"【第{s['chapter']}章】\n{s['text']}" for s in samples)
    schema = {
        "type": "object",
        "properties": {
            "era_tech_level": {"type": "string", "description": "技术/年代基准，如'蒸汽朋克·类第一次工业革命，无电力/塑料/抗生素/现代通讯'"},
            "baseline_register": {"type": "string", "description": "世界整体/旁白基准语域(书面化程度、雅俗)"},
            "forbidden_universal": {"type": "array", "items": {"type": "string"}, "description": "对所有阵营都禁的词类(现代科技/网络流行语/现代口语腔等)，给具体例子"},
            "factions": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"},
                "culture": {"type": "string", "description": "如'西欧贵族/教廷''东亚朝廷'"},
                "register_notes": {"type": "string", "description": "该阵营该有的用词/称谓/礼仪特征"},
                "signature_terms": {"type": "array", "items": {"type": "string"}, "description": "该阵营专属词/称谓示例"},
            }}},
        },
    }
    sys = (
        "你在为一本架空小说建立『世界观语域卡』，用于审查续写是否有时代错置或文化语域错置。\n"
        "请从原著片段中提炼：① 世界的技术/年代基准(决定哪些现代物品/概念绝不能出现)；"
        "② 世界整体/旁白的基准语域；③ 对所有阵营都禁的词类(现代科技、网络流行语、现代口语腔)；"
        "④ 各**阵营/文化**及其各自的语域特征与专属词(如有东西方/多文化并存，逐个列出)。\n"
        "# 输出格式（严格）\n只输出一个 JSON 对象，无其它文字、无 markdown 围栏，符合此 schema：\n"
        + json.dumps(schema, ensure_ascii=False)
    )
    resp = llm.call(agent="style.register_card", model=MODEL_STRONG, system=sys,
                    messages=[{"role": "user", "content": corpus_text}],
                    max_tokens=6000, temperature=0.2)
    def _loads(t: str) -> dict:
        t = re.sub(r"```json|```", "", t or "").strip()
        try:
            return json.loads(t)
        except Exception:
            try:
                from json_repair import repair_json
                d = json.loads(repair_json(t)); return d if isinstance(d, dict) else {}
            except Exception:
                return {}
    card = _loads(resp.text or "")
    with session_scope() as s:
        row = s.execute(select(StyleProfile).limit(1)).scalar_one_or_none()
        if row is None:
            row = StyleProfile(); s.add(row)
        row.register_card_json = card
        row.updated_at = datetime.utcnow()
    return {"factions": [f.get("name") for f in (card.get("factions") or [])],
            "era": card.get("era_tech_level", "")[:80], "cost_usd": resp.cost_usd}


def get_profile() -> dict[str, Any] | None:
    with session_scope() as s:
        row = s.execute(select(StyleProfile).order_by(StyleProfile.id.desc()).limit(1)).scalar_one_or_none()
        if row is None:
            return None
        return {
            "id": row.id,
            "profile": row.profile_json or {},
            "summary": row.summary or "",
            "sampled_chapters": row.sampled_chapters or [],
            "mimic_enabled": bool(row.mimic_enabled),
            "bilingual": bool(row.bilingual),
            "is_western_setting": bool((row.profile_json or {}).get("is_western_setting")),
            "register_card": row.register_card_json or None,
            "has_register_card": bool(row.register_card_json),
            "era_check_enabled": bool(row.era_check_enabled),
            "culture_check_enabled": bool(row.culture_check_enabled),
            "model": row.model,
            "cost_usd": row.cost_usd,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }


def set_toggles(mimic_enabled: bool | None = None, bilingual: bool | None = None,
                era_check_enabled: bool | None = None,
                culture_check_enabled: bool | None = None) -> dict[str, Any] | None:
    with session_scope() as s:
        row = s.execute(select(StyleProfile).order_by(StyleProfile.id.desc()).limit(1)).scalar_one_or_none()
        if row is None:
            return None
        if mimic_enabled is not None:
            row.mimic_enabled = 1 if mimic_enabled else 0
        if bilingual is not None:
            row.bilingual = 1 if bilingual else 0
        if era_check_enabled is not None:
            row.era_check_enabled = 1 if era_check_enabled else 0
        if culture_check_enabled is not None:
            row.culture_check_enabled = 1 if culture_check_enabled else 0
        row.updated_at = datetime.utcnow()
    return get_profile()


def continuation_style_guide() -> str | None:
    """For the writer: the author's style guide IF mimic is enabled, else None."""
    p = get_profile()
    if not p or not p.get("mimic_enabled"):
        return None
    prof = p.get("profile") or {}
    parts = []
    if prof.get("overall_voice"):
        parts.append("【原作者整体文风】\n" + prof["overall_voice"])
    if prof.get("continuation_guide"):
        parts.append("【模仿原作者文风 · 总指导】\n" + prof["continuation_guide"])
    sc = prof.get("scene_styles") or {}
    if isinstance(sc, dict) and sc:
        labels = {"combat": "打斗", "scenery": "景物", "character": "人物",
                  "dialogue": "对话", "psychology": "心理", "plot_advancement": "剧情推进"}
        lines = [f"- {labels.get(k, k)}：{v}" for k, v in sc.items() if v]
        if lines:
            parts.append("【分场景笔法】\n" + "\n".join(lines))
    ns = prof.get("narrative_structure") or {}
    if isinstance(ns, dict) and ns.get("continuation_rhythm_guide"):
        rg = ns["continuation_rhythm_guide"]
        povs = ns.get("pov_structure")
        parts.append("【遵循原书叙事节奏与视角】\n" + rg + (f"\n视角结构：{povs}" if povs else ""))
    if prof.get("signature_vocabulary"):
        vocab = prof["signature_vocabulary"]
        if isinstance(vocab, list):
            parts.append("【标志性词汇/意象（可化用，勿堆砌）】\n" + "、".join(str(v) for v in vocab[:15]))
    if prof.get("pitfalls_to_avoid"):
        pit = prof["pitfalls_to_avoid"]
        if isinstance(pit, list):
            parts.append("【务必避免】\n" + "\n".join(f"- {x}" for x in pit))
    return "\n\n".join(parts) if parts else None


def continuation_setting() -> str | None:
    """Canonical world/setting + proper-noun system, for grounding any draft
    (esp. the English one) so it doesn't invent off-setting names/places.
    Returns None if no profile. Independent of mimic toggle — the setting is a
    fact about the book, not a stylistic choice."""
    p = get_profile()
    if not p:
        return None
    prof = p.get("profile") or {}
    parts = []
    if prof.get("setting_register"):
        parts.append("【世界观/设定/专有名词体系】\n" + str(prof["setting_register"]))
    vocab = prof.get("signature_vocabulary")
    if isinstance(vocab, list) and vocab:
        parts.append("【固定专有名词/意象（务必沿用，勿另造）】\n" + "、".join(str(v) for v in vocab[:20]))
    return "\n\n".join(parts) if parts else None
