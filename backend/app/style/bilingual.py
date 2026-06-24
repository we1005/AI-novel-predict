"""Bilingual (ZH/EN) cross-translation continuation pipeline (STYLE-3).

Flow for one chapter:
  1. ZH draft  — written in Chinese, mimicking the original author (style profile).
     This is the SOURCE OF TRUTH for plot/characters/setting.
  2. EN draft  — a native-English RE-CREATION of the ZH chapter (same story, told
     with authentic English literary craft; NOT a literal translation). Anchored
     to the ZH draft so the two languages can never diverge into different
     chapters — the failure mode that made fully-independent parallel drafts
     produce two unrelated stories.
  3. cross-translate: ZH→EN and EN→ZH.
  4. merge — an editor blends best-of-both → final ZH + final EN (mutually
     consistent), infusing authentic English technique to dilute 西幻网文腔.
     Each merge degrades to the independent draft if it comes back empty/short.

Designed to run from a free-text brief (+ recent-chapter continuity), so it works
even before a formal OutlineRun exists for the book.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..config import MODEL_STRONG
from ..llm import client as llm
from ..llm.prompts.writer import build_writer_system
from ..llm.prompts.style import (
    EN_WRITER_SYSTEM,
    TRANSLATE_ZH2EN_SYSTEM,
    TRANSLATE_EN2ZH_SYSTEM,
    BILINGUAL_MERGE_EN_SYSTEM,
    BILINGUAL_MERGE_ZH_SYSTEM,
)
from .pipeline import continuation_style_guide, continuation_setting


def _recent_tail(after_chapter: int, n_chars: int = 1200) -> str:
    from ..draft.pipeline import _prev_chapter_tail
    return _prev_chapter_tail(0, after_chapter + 1, n_chars) or ""


def _zh_draft(brief: str, tail: str, guide: str | None, chapter_n: int) -> tuple[str, float]:
    user = (
        (f"# 上一章结尾（自然承接）\n{tail}\n\n" if tail else "")
        + f"# 本章要求（第 {chapter_n} 章，悬疑推进）\n{brief}\n\n"
        "请按上述原作者文风与叙事节奏，用中文写出本章正文（约 2500-3500 字），章末留悬念钩子。"
    )
    r = llm.call(agent="draft.writer", model=MODEL_STRONG,
                 system=build_writer_system(guide),
                 messages=[{"role": "user", "content": user}],
                 max_tokens=16000, temperature=0.75)
    return (r.text or "").strip(), r.cost_usd


def _en_draft(zh_draft: str, setting: str | None, chapter_n: int) -> tuple[str, float]:
    """Re-CREATE the Chinese chapter as a native English literary author.

    Key fix: the EN draft is anchored to the ZH draft's actual story, so the two
    languages can never diverge into different chapters. This is a re-telling in
    authentic English prose (the user explicitly wants English craft to dilute
    廉价西幻腔), NOT a literal translation — the author may re-pace sentences and
    imagery, but must invent NO new plot, characters, or places.
    """
    user = (
        (f"# Canonical setting — use these established Western proper nouns\n{setting}\n\n" if setting else "")
        + f"# The chapter to re-create (Chapter {chapter_n}, written in Chinese)\n{zh_draft}\n\n"
        "Re-create this EXACT chapter as a native English literary novelist. Keep the SAME "
        "characters, setting, events, beats, and ending hook. Render Chinese transliterations of "
        "Western names back to their natural Western forms (e.g. 西泽尔→Cesare, 拜伦→Byron, "
        "翡冷翠→Florence, 博尔吉亚→Borgia, 君士坦丁堡→Constantinople). This is an authentic English "
        "RE-TELLING with full literary craft, NOT a literal translation — re-pace and re-image as "
        "an English author would, but invent nothing new. ~2500-3500 words. Keep it suspenseful."
    )
    r = llm.call(agent="bilingual.en_writer", model=MODEL_STRONG,
                 system=EN_WRITER_SYSTEM,
                 messages=[{"role": "user", "content": user}],
                 max_tokens=16000, temperature=0.8)
    return (r.text or "").strip(), r.cost_usd


def _translate(system: str, text: str, agent: str) -> tuple[str, float]:
    # max_tokens generous: minimax-m3 spends a variable, often large chunk of the
    # budget on hidden reasoning before emitting the translation. 9000 was too
    # tight (translating a full maxed-out chapter → finish=length, empty content,
    # job-killing). Mirror the merge conclusion and give it real headroom.
    # NON-FATAL: if the translate still comes back empty after client retries,
    # swallow it and return "" — the caller degrades to the independent draft
    # rather than failing the whole bilingual job.
    try:
        r = llm.call(agent=agent, model=MODEL_STRONG, system=system,
                     messages=[{"role": "user", "content": text}],
                     max_tokens=20000, temperature=0.4)
        return (r.text or "").strip(), r.cost_usd
    except Exception:  # noqa: BLE001
        return "", 0.0


def _merge_en(en_orig: str, en_from_zh: str) -> tuple[str, float]:
    user = (f"[EN-original]\n{en_orig}\n\n[EN-from-Chinese]\n{en_from_zh}\n\n"
            "Now produce the single final English chapter (best of both).")
    r = llm.call(agent="bilingual.merge", model=MODEL_STRONG, system=BILINGUAL_MERGE_EN_SYSTEM,
                 messages=[{"role": "user", "content": user}],
                 max_tokens=32000, temperature=0.6)
    return (r.text or "").strip(), r.cost_usd


def _merge_zh(zh_orig: str, zh_from_en: str) -> tuple[str, float]:
    user = (f"[中文原创]\n{zh_orig}\n\n[中文←英文]\n{zh_from_en}\n\n"
            "现在产出唯一的最终中文正文（取长补短）。")
    r = llm.call(agent="bilingual.merge", model=MODEL_STRONG, system=BILINGUAL_MERGE_ZH_SYSTEM,
                 messages=[{"role": "user", "content": user}],
                 max_tokens=32000, temperature=0.6)
    return (r.text or "").strip(), r.cost_usd


def bilingual_from_zh(zh_text: str, chapter_n: int, *, persist: bool = True) -> dict[str, Any]:
    """把**已过审的中文定稿**交织出英文版（中英对照）。

    与 `bilingual_write` 的区别：不重新创作中文、不 merge——已过审的中文是唯一事实源，
    保持不动作为 `final_zh`；只用 `_en_draft` 锚定它再创作出地道英文 `final_en`
    （非直译，保留原作者笔法、把中文音译西名还原成西文）。这是接入主流程的
    "每章自动出中英对照"的核心：中文先真三审通过，再交织英文，两边绝不跑偏。
    """
    setting = None
    try:
        setting = continuation_setting()
    except Exception:  # noqa: BLE001
        setting = None
    en, cost = _en_draft(zh_text, setting, chapter_n)
    res = {"final_zh": zh_text, "final_en": en, "cost_usd": cost,
           "drafts": {"en_recreate": en}}
    if persist and en:
        from datetime import datetime
        from sqlalchemy import select, desc
        from ..db import session_scope
        from ..memory.models import BilingualDraft
        with session_scope() as s:
            # upsert：同章已有 done 行就覆盖，避免重复
            row = s.execute(select(BilingualDraft).where(
                BilingualDraft.chapter == chapter_n).order_by(desc(BilingualDraft.id))
            ).scalars().first()
            if row is None:
                row = BilingualDraft(chapter=chapter_n)
                s.add(row)
            row.brief = f"从第{chapter_n}章已过审中文定稿交织英文"
            row.final_zh = zh_text
            row.final_en = en
            row.drafts_json = res["drafts"]
            row.cost_usd = cost
            row.status = "done"
            row.stage = "done"
            row.updated_at = datetime.utcnow()
            s.flush()
            res["id"] = row.id
    return res


def create_job(brief: str, after_chapter: int, chapter_n: int | None) -> int:
    """Insert a 'writing' BilingualDraft row, return its id (for polling)."""
    from datetime import datetime
    from ..db import session_scope
    from ..memory.models import BilingualDraft
    with session_scope() as s:
        row = BilingualDraft(chapter=chapter_n or (after_chapter + 1),
                             brief=brief, status="writing", updated_at=datetime.utcnow())
        s.add(row)
        s.flush()
        return row.id


def _set_stage(job_id: int, stage: str) -> None:
    """Persist a granular progress stage on the job row (best-effort)."""
    from datetime import datetime
    from ..db import session_scope
    from ..memory.models import BilingualDraft
    try:
        with session_scope() as s:
            row = s.get(BilingualDraft, job_id)
            if row:
                row.stage = stage
                row.updated_at = datetime.utcnow()
    except Exception:  # noqa: BLE001
        pass  # progress display is non-critical; never let it break the job


def run_and_store(job_id: int, brief: str, after_chapter: int, chapter_n: int | None) -> None:
    """Background entrypoint: run the pipeline, persist results onto the row."""
    from datetime import datetime
    from ..db import session_scope
    from ..memory.models import BilingualDraft
    try:
        res = bilingual_write(brief, after_chapter, chapter_n,
                              on_stage=lambda st: _set_stage(job_id, st))
        with session_scope() as s:
            row = s.get(BilingualDraft, job_id)
            if row:
                row.final_zh = res["final_zh"]
                row.final_en = res["final_en"]
                row.drafts_json = res["drafts"]
                row.cost_usd = res["cost_usd"]
                row.status = "done"
                row.stage = "done"
                row.updated_at = datetime.utcnow()
    except Exception as e:  # noqa: BLE001
        with session_scope() as s:
            row = s.get(BilingualDraft, job_id)
            if row:
                row.status = "failed"
                row.error = str(e)[:500]
                row.updated_at = datetime.utcnow()


def list_jobs(limit: int = 20) -> list[dict]:
    from sqlalchemy import select, desc
    from ..db import session_scope
    from ..memory.models import BilingualDraft
    with session_scope() as s:
        rows = s.execute(select(BilingualDraft).order_by(desc(BilingualDraft.id)).limit(limit)).scalars().all()
        return [{"id": r.id, "chapter": r.chapter, "status": r.status, "stage": r.stage or "",
                 "cost_usd": r.cost_usd, "brief": (r.brief or "")[:80],
                 "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


def get_job(job_id: int) -> dict | None:
    from ..db import session_scope
    from ..memory.models import BilingualDraft
    with session_scope() as s:
        r = s.get(BilingualDraft, job_id)
        if not r:
            return None
        return {"id": r.id, "chapter": r.chapter, "status": r.status, "stage": r.stage or "",
                "brief": r.brief,
                "final_zh": r.final_zh, "final_en": r.final_en, "drafts": r.drafts_json or {},
                "error": r.error, "cost_usd": r.cost_usd,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None}


def bilingual_write(brief: str, after_chapter: int, chapter_n: int | None = None,
                    on_stage=None) -> dict[str, Any]:
    """Run the full bilingual pipeline for one chapter. Returns final ZH + EN
    plus all intermediates and total cost.

    ``on_stage(stage:str)`` — optional callback fired at each stage boundary so
    a caller can surface granular progress (jobs run ~5-15 min).
    """
    def _stage(st):
        if on_stage:
            try:
                on_stage(st)
            except Exception:  # noqa: BLE001
                pass
    chapter_n = chapter_n or (after_chapter + 1)
    tail = _recent_tail(after_chapter)
    guide = continuation_style_guide()
    setting = continuation_setting()
    cost = 0.0

    # Stage 1: ZH draft is the source of truth (grounded by mimic guide + recent
    # tail). The EN draft is then a native-English RE-CREATION of that same story
    # — serial, not parallel, so the two languages can never diverge into
    # different chapters (the bug that made independent parallel drafts useless).
    _stage("zh_draft")
    zh_orig, c1 = _zh_draft(brief, tail, guide, chapter_n)
    _stage("en_recreate")
    en_orig, c2 = _en_draft(zh_orig, setting, chapter_n)
    cost += c1 + c2

    # Stage 2: cross-translate (parallel).
    _stage("translate")
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_e = ex.submit(_translate, TRANSLATE_ZH2EN_SYSTEM, zh_orig, "translate.zh2en")
        f_z = ex.submit(_translate, TRANSLATE_EN2ZH_SYSTEM, en_orig, "translate.en2zh")
        en_from_zh, c3 = f_e.result()
        zh_from_en, c4 = f_z.result()
    cost += c3 + c4

    # Stage 3: two language-specific merges (parallel) — smaller, reliable.
    # Only merge when BOTH the original draft AND its cross-translation exist;
    # if a translate stage degraded to "" (reasoning ate the budget), there's
    # nothing to blend, so skip the merge and keep the independent draft.
    def _merge_or_keep(merge_fn, orig, translated):
        if orig and translated:
            return merge_fn(orig, translated)
        return (orig or translated or ""), 0.0
    _stage("merge")
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_en = ex.submit(_merge_or_keep, _merge_en, en_orig, en_from_zh)
        f_zh = ex.submit(_merge_or_keep, _merge_zh, zh_orig, zh_from_en)
        final_en, c5e = f_en.result()
        final_zh, c5z = f_zh.result()
    cost += c5e + c5z

    # Robustness: reasoning models occasionally return empty OR truncated (their
    # hidden reasoning eats the token budget). Never ship an empty/truncated
    # deliverable — fall back to the full independent draft when the merged
    # version is missing or suspiciously short (<40% of the source length).
    def _ok(merged: str, source: str) -> bool:
        return bool((merged or "").strip()) and len(merged) >= 0.4 * max(1, len(source or ""))
    if not _ok(final_zh, zh_orig):
        final_zh = zh_orig or zh_from_en or final_zh
    if not _ok(final_en, en_orig):
        final_en = en_orig or en_from_zh or final_en

    return {
        "chapter": chapter_n,
        "final_zh": final_zh,
        "final_en": final_en,
        "drafts": {
            "zh_orig": zh_orig, "en_orig": en_orig,
            "en_from_zh": en_from_zh, "zh_from_en": zh_from_en,
        },
        "cost_usd": round(cost, 5),
    }
