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

    resp = llm.call(
        agent="style.analyze",
        model=MODEL_STRONG,
        system=STYLE_ANALYZE_SYSTEM,
        messages=[{"role": "user", "content": build_style_user_message(samples)}],
        tools=[STYLE_TOOL],
        tool_choice={"type": "tool", "name": STYLE_TOOL["name"]},
        max_tokens=8000,
        temperature=0.3,
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
            "model": row.model,
            "cost_usd": row.cost_usd,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }


def set_toggles(mimic_enabled: bool | None = None, bilingual: bool | None = None) -> dict[str, Any] | None:
    with session_scope() as s:
        row = s.execute(select(StyleProfile).order_by(StyleProfile.id.desc()).limit(1)).scalar_one_or_none()
        if row is None:
            return None
        if mimic_enabled is not None:
            row.mimic_enabled = 1 if mimic_enabled else 0
        if bilingual is not None:
            row.bilingual = 1 if bilingual else 0
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
