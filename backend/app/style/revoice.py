"""Re-voice: 推翻文笔，保留主干剧情重写.

Take an existing chapter (original ingested text OR a generated draft) and:
  1. extract its plot skeleton (events/beats/key-facts/hook), stripping voice;
  2. rewrite fresh prose from that skeleton in a TARGET voice, preserving plot.

Target voices:
  - "wangwen"  : default punchy 网文 voice (WRITER_SYSTEM)
  - "mimic"    : imitate the original author (style profile guide)
  - "english"  : native literary English (EN_WRITER_SYSTEM)
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..llm import client as llm

# Skeleton = structured tool output → code model (clean JSON). Rewrite = prose →
# minimax-m3. Explicit because these agents aren't in the lane registry.
_SKELETON_MODEL = "doubao-seed-2.0-code"
_PROSE_MODEL = "minimax-m3"
from ..llm.prompts.style import (
    SKELETON_TOOL, SKELETON_SYSTEM, build_revoice_user, EN_WRITER_SYSTEM,
)
from ..llm.prompts.writer import WRITER_SYSTEM, build_writer_system
from .pipeline import continuation_style_guide

VOICES = ("wangwen", "mimic", "english")


# JSON-in-text skeleton extraction. Forced tool_choice flakes on doubao/volc
# reasoning models (output lands in a reasoning channel, no tool_call emitted),
# so we ask for plain JSON and repair-parse it — reliable across all models.
_SKELETON_JSON_SYSTEM = SKELETON_SYSTEM + """

# 输出格式（严格）
只输出一个 JSON 对象，不要任何其它文字、不要 markdown 代码块围栏。字段：
{"title": "本章标题", "setting": "时间地点场景一句话", "pov": "视角人物",
 "beats": ["按顺序的剧情节拍, 8-20条, 只记发生了什么"],
 "key_facts": ["本章透露的关键信息/设定/伏笔"],
 "ending_hook": "章末悬念事件"}"""


def _loads(s: str) -> dict:
    s = re.sub(r"```json|```", "", s or "").strip()
    try:
        d = json.loads(s)
    except Exception:
        try:
            from json_repair import repair_json
            d = json.loads(repair_json(s))
        except Exception:
            return {}
    return d if isinstance(d, dict) else {}


def extract_skeleton(text: str) -> tuple[dict, float]:
    resp = llm.call(
        agent="revoice.skeleton", model=_SKELETON_MODEL, system=_SKELETON_JSON_SYSTEM,
        messages=[{"role": "user", "content": "拆解这一章，按规定 JSON 格式输出：\n\n" + text}],
        max_tokens=4000, temperature=0.2,
    )
    return _loads(resp.text or ""), resp.cost_usd


def _rewrite(skeleton: dict, voice: str, chapter_n: int | None) -> tuple[str, float]:
    user = build_revoice_user(skeleton, chapter_n)
    if voice == "english":
        system, agent = EN_WRITER_SYSTEM, "revoice.write.en"
        user = (
            "Rewrite this chapter natively in English from the skeleton below. Keep the plot "
            "and key facts exactly; change only the prose/voice.\n\n" + user
        )
    elif voice == "mimic":
        system, agent = build_writer_system(continuation_style_guide()), "revoice.write.mimic"
    else:  # wangwen
        system, agent = WRITER_SYSTEM, "revoice.write.wangwen"
    resp = llm.call(
        agent=agent, model=_PROSE_MODEL, system=system,
        messages=[{"role": "user", "content": user}],
        max_tokens=8000, temperature=0.75,
    )
    txt = resp.text or ""
    # strip stray markdown emphasis like the draft pipeline does
    txt = re.sub(r"\*\*(.+?)\*\*", r"\1", txt).replace("**", "")
    return txt.strip(), resp.cost_usd


def revoice(text: str, voice: str = "wangwen", chapter_n: int | None = None) -> dict[str, Any]:
    if voice not in VOICES:
        voice = "wangwen"
    skeleton, c1 = extract_skeleton(text)
    rewritten, c2 = _rewrite(skeleton, voice, chapter_n)
    return {
        "voice": voice,
        "skeleton": skeleton,
        "rewritten": rewritten,
        "cost_usd": round(c1 + c2, 5),
    }


# ---------------------------------------------------------------------------
# Job persistence + chapter sourcing
# ---------------------------------------------------------------------------

def _chapter_text(chapter: int) -> str | None:
    """Resolve a chapter's prose by number. Prefers the original ingested text
    (chapter_fts); falls back to a GENERATED chapter (chapter_drafts.final_text)
    so re-voice works on续写出来的新章节 too, not just original chapters."""
    from sqlalchemy import text as _sql_text
    from ..db import get_engine
    with get_engine().begin() as conn:
        r = conn.execute(_sql_text("SELECT body FROM chapter_fts WHERE chapter = :c LIMIT 1"),
                         {"c": chapter}).mappings().first()
        if r and (r["body"] or "").strip():
            return r["body"]
        # Fallback: a generated draft for this chapter (latest non-empty).
        r2 = conn.execute(_sql_text(
            "SELECT final_text FROM chapter_drafts WHERE chapter_index = :c "
            "AND final_text IS NOT NULL ORDER BY id DESC LIMIT 1"), {"c": chapter}).mappings().first()
        return (r2["final_text"] if r2 else None)


def create_job(voice: str, source_chapter: int | None) -> int:
    from datetime import datetime
    from ..db import session_scope
    from ..memory.models import RevoiceJob
    with session_scope() as s:
        row = RevoiceJob(voice=voice if voice in VOICES else "wangwen",
                         source_chapter=source_chapter, status="writing",
                         updated_at=datetime.utcnow())
        s.add(row); s.flush()
        return row.id


def run_and_store(job_id: int, text: str, voice: str, chapter_n: int | None) -> None:
    from datetime import datetime
    from ..db import session_scope
    from ..memory.models import RevoiceJob
    try:
        res = revoice(text, voice=voice, chapter_n=chapter_n)
        with session_scope() as s:
            row = s.get(RevoiceJob, job_id)
            if row:
                row.skeleton_json = res["skeleton"]; row.rewritten = res["rewritten"]
                row.cost_usd = res["cost_usd"]; row.status = "done"
                row.updated_at = datetime.utcnow()
    except Exception as e:  # noqa: BLE001
        with session_scope() as s:
            row = s.get(RevoiceJob, job_id)
            if row:
                row.status = "failed"; row.error = str(e)[:500]
                row.updated_at = datetime.utcnow()


def list_jobs(limit: int = 20) -> list[dict]:
    from sqlalchemy import select, desc
    from ..db import session_scope
    from ..memory.models import RevoiceJob
    with session_scope() as s:
        rows = s.execute(select(RevoiceJob).order_by(desc(RevoiceJob.id)).limit(limit)).scalars().all()
        return [{"id": r.id, "voice": r.voice, "source_chapter": r.source_chapter,
                 "status": r.status, "cost_usd": r.cost_usd,
                 "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


def get_job(job_id: int) -> dict | None:
    from ..db import session_scope
    from ..memory.models import RevoiceJob
    with session_scope() as s:
        r = s.get(RevoiceJob, job_id)
        if not r:
            return None
        return {"id": r.id, "voice": r.voice, "source_chapter": r.source_chapter,
                "status": r.status, "skeleton": r.skeleton_json or {},
                "rewritten": r.rewritten, "error": r.error, "cost_usd": r.cost_usd,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None}


def start_job(voice: str, source_chapter: int | None, text: str | None) -> dict:
    """Resolve source text (chapter or raw), create job, return (id, text)."""
    body = text or (_chapter_text(source_chapter) if source_chapter else None)
    if not body:
        raise ValueError("no source text — provide `text` or a valid `source_chapter`")
    jid = create_job(voice, source_chapter)
    return {"id": jid, "text": body, "chapter_n": source_chapter}
