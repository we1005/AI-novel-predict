"""Chapter writing pipeline: Writer + 3 reviewers (parallel) + Editor + ReAct.

The high-level loop:

    for attempt in 1..max_attempts:
        prose <- Writer(outline + style_refs + previous_attempt_feedback)
        if skip_reviews: return prose

        run StyleReviewer / PlotReviewer / ConsistencyReviewer in parallel
        editor_result <- Editor(reviews, attempt, max_attempts)

        if editor.decision == "approve" or "ship_with_warnings": break
        else continue with revision_brief

The four agents share the cached context from ``predict.pipeline._gather_context``
so we get cache hits across all 4 LLM calls per attempt.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select

from ..config import MODEL_FAST, MODEL_STRONG
from ..db import session_scope
from ..llm import client as llm
from ..llm.prompts.reviewers import (
    CONSISTENCY_REVIEWER_SYSTEM,
    CONSISTENCY_REVIEWER_TOOL,
    EDITOR_SYSTEM,
    EDITOR_TOOL,
    PLOT_REVIEWER_SYSTEM,
    PLOT_REVIEWER_TOOL,
    STYLE_REVIEWER_SYSTEM,
    STYLE_REVIEWER_TOOL,
    ERA_REGISTER_REVIEWER_TOOL,
    build_era_register_system,
    gate_decision,
    hard_issue_score,
    heuristic_decision,
)
from ..llm.prompts.writer import WRITER_SYSTEM, build_writer_system, build_writer_user_message
from ..memory import fts as fts_recall
from ..memory.models import ChapterDraft, OutlineRun
from ..predict.pipeline import _ctx_blocks, _gather_context


import re as _re

# Models sometimes emit Markdown emphasis (**词**) into prose despite being told
# not to. Strip it so the exported novel is clean. Chinese prose essentially
# never uses bare * / _ legitimately, so this is safe.
_MD_BOLD = _re.compile(r"\*\*(.+?)\*\*", _re.S)
_MD_BOLD_U = _re.compile(r"__(.+?)__", _re.S)
_MD_HEADER = _re.compile(r"^\s{0,3}#{1,6}\s+", _re.M)


def _strip_inline_markdown(text: str) -> str:
    if not text:
        return text
    text = _MD_BOLD.sub(r"\1", text)
    text = _MD_BOLD_U.sub(r"\1", text)
    text = text.replace("**", "")            # leftover unpaired markers
    text = _MD_HEADER.sub("", text)          # stray "## " line-leading headers
    return text


def _coerce_dict(v: Any) -> dict:
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            d = json.loads(v)
            if isinstance(d, dict):
                return d
        except json.JSONDecodeError:
            try:
                from json_repair import repair_json
                d = json.loads(repair_json(v))
                if isinstance(d, dict):
                    return d
            except Exception:
                pass
    return {}


def _recent_chapter_prose(after_chapter: int, n: int = 4, per_chars: int = 900) -> list[dict]:
    """Pull the actual prose of the most-recent ``n`` chapters as the style
    anchor — book-agnostic (no hardcoded protagonist name) and real continuous
    text, which anchors voice far better than tiny FTS snippets.

    Reads from the ``chapter_fts.body`` column (full chapter text), which is
    populated for every ingested book. Returns [] gracefully on any error so
    the caller can fall back to an FTS query."""

    from sqlalchemy import text as _sql_text
    from ..db import get_engine

    out: list[dict] = []
    try:
        with get_engine().begin() as conn:
            rows = conn.execute(
                _sql_text(
                    "SELECT chapter, title, body FROM chapter_fts "
                    "WHERE chapter <= :c AND chapter IS NOT NULL "
                    "ORDER BY chapter DESC LIMIT :n"
                ),
                {"c": after_chapter, "n": n},
            ).mappings().all()
    except Exception:
        return []

    for r in rows:
        # Take the tail of the chapter (most recent voice), with scraper/footer
        # junk stripped so it never pollutes the style anchor.
        snip = _clean_tail(r.get("body") or "", per_chars)
        if not snip:
            continue
        out.append({"chapter": r.get("chapter"), "title": r.get("title") or "", "snip": snip})
    # rows came newest-first; present oldest-first so refs read in order.
    out.reverse()
    return out


def _gather_style_refs(*, after_chapter: int, must_include: list[str]) -> list[dict]:
    """Style anchors: the most-recent chapters' real prose (book-agnostic) plus
    a couple of topic-relevant historical hits via FTS for flavor."""

    refs: list[dict] = _recent_chapter_prose(after_chapter, n=4)

    # Fallback: if corpus/offsets unavailable, use a generic recent-FTS pull.
    if not refs:
        try:
            # Match any chapter before the cut; an empty-ish query isn't allowed,
            # so probe with a few very common CJK function words.
            refs = fts_recall.search(query="的 了 他", limit=4, before_chapter=after_chapter + 1)
        except Exception:
            refs = []

    # Topic-relevant supplement: use must_include phrases as queries.
    # 修复(agentic-search 议题·自我污染):风味锚点应来自**原著**,排除续写已生成的章
    # (否则写到第 N 章会把自己刚生成的 N-1 章当"原著风格"召回 → 自我同质化/塌缩)。
    # 改用 craft.search.search_corpus(trigram 友好 + exclude_chapters),只在话题补充段生效;
    # 近章续贯(_recent_chapter_prose)保持不变。
    gen_chapters: set[int] = set()
    try:
        from sqlalchemy import select as _select
        from ..memory.models import ChapterDraft
        with session_scope() as _s:
            gen_chapters = {c for (c,) in _s.execute(_select(ChapterDraft.chapter_index)).all() if c is not None}
    except Exception:
        gen_chapters = set()
    for phrase in (must_include or [])[:2]:
        if not phrase or len(phrase) < 4:
            continue
        try:
            from ..craft import search as _cs
            hits = _cs.search_corpus(phrase[:40], k=1,
                                     exclude_chapters=gen_chapters, before_chapter=after_chapter + 1)
            refs.extend(hits)
        except Exception:
            continue

    # E2(语义补充):开关打开时,用 must_include 主题做向量检索,捞**语义相关但不含
    # 关键词**的原著片段(FTS 给不了的召回)。默认关闭则完全跳过(不加载模型);
    # 同样排除已生成章,避免自我同质化。失败静默(降级回纯 FTS/近章)。
    try:
        from ..settings.store import get_vector_recall_enabled
        if get_vector_recall_enabled():
            from ..memory import vector as _vec
            topic = " ".join(p for p in (must_include or [])[:3] if p)[:80]
            if topic:
                for h in _vec.query(topic, k=2, before_chapter=after_chapter + 1):
                    if h.get("chapter") in gen_chapters:
                        continue
                    refs.append({"chapter": h.get("chapter"), "title": h.get("title"),
                                 "text": h.get("text"), "source": "vector"})
    except Exception:
        pass

    # Dedup by chapter.
    seen = set()
    out = []
    for r in refs:
        ch = r.get("chapter")
        if ch in seen:
            continue
        seen.add(ch)
        out.append(r)
    return out[:7]


# Scraper/footer junk that some corpora append to the final chapter. We cut the
# text at the first occurrence so it never leaks into the writer's continuity ctx.
_CORPUS_JUNK_MARKERS = (
    "【全书完】", "全书完", "（全文完）", "(全文完)", "全文完",
    "书香门第", "本作品来自互联网", "版权归作者", "本书由", "未经允许",
    "请勿用于商业", "更多精彩", "txt下载", "TXT下载",
)


def _clean_tail(txt: str, n_chars: int) -> str | None:
    txt = (txt or "").strip()
    if not txt:
        return None
    cut = len(txt)
    for mk in _CORPUS_JUNK_MARKERS:
        i = txt.find(mk)
        if i != -1:
            cut = min(cut, i)
    txt = txt[:cut].strip()
    if not txt:
        return None
    return txt[-n_chars:] if len(txt) > n_chars else txt


def _prev_chapter_tail(outline_run_id: int, chapter_index: int, n_chars: int = 700) -> str | None:
    """Tail of the immediately-preceding chapter so the writer continues serially
    instead of re-establishing the scene.

    Prefers the previous *generated* chapter's final text (same outline run); if
    there's no such draft (e.g. this is the first continuation chapter, whose
    predecessor is an original ingested chapter), falls back to the original
    chapter body from chapter_fts. Returns None if neither exists."""

    # 1) Previous generated chapter (same run).
    with session_scope() as s:
        row = s.execute(
            select(ChapterDraft).where(
                ChapterDraft.outline_run_id == outline_run_id,
                ChapterDraft.chapter_index == chapter_index - 1,
            ).limit(1)
        ).scalar_one_or_none()
        if row and row.final_text:
            return _clean_tail(row.final_text, n_chars)

    # 2) Fall back to the original ingested chapter (the book→continuation seam).
    from sqlalchemy import text as _sql_text
    from ..db import get_engine
    try:
        with get_engine().begin() as conn:
            r = conn.execute(
                _sql_text("SELECT body FROM chapter_fts WHERE chapter = :c LIMIT 1"),
                {"c": chapter_index - 1},
            ).mappings().first()
    except Exception:
        return None
    if not r:
        return None
    return _clean_tail(r.get("body") or "", n_chars)


_SCENE_CUES = {
    "combat": ["战", "打斗", "交手", "对决", "厮杀", "激战", "出手", "搏", "血", "袭", "攻", "击", "刃", "甲"],
    "dialogue": ["对话", "谈", "质问", "交涉", "谈判", "审", "密谈", "试探", "争论", "觐见", "劝", "说服", "对峙"],
    "scenery": ["夜", "赶路", "抵达", "潜入", "环境", "街", "城", "雨", "雪", "风", "景", "黎明", "黄昏", "废墟"],
    "psychology": ["回忆", "独白", "挣扎", "心", "抉择", "痛", "孤", "念", "犹豫", "恐惧"],
}


def _scene_exemplar_block(chapter_outline: dict) -> str:
    """按本章场景类型，取原著同类**真实范例段落**作 few-shot（"给范文"而非只"讲道理"）。"""
    from ..memory.models import StyleProfile
    with session_scope() as s:
        row = s.execute(select(StyleProfile).order_by(desc(StyleProfile.id)).limit(1)).scalars().first()
        ex = (row.scene_exemplars_json if row else None) or {}
    if not ex:
        return ""
    text = " ".join([str(chapter_outline.get("intent") or ""), str(chapter_outline.get("pacing") or ""),
                     " ".join(str(x) for x in (chapter_outline.get("must_include") or []))])
    scores = {k: sum(text.count(c) for c in cues) for k, cues in _SCENE_CUES.items()}
    # 取命中最高的 2 类；都为 0 则回退到最常见的 打斗+对话
    ranked = [k for k, v in sorted(scores.items(), key=lambda kv: kv[1], reverse=True) if v > 0][:2]
    if not ranked:
        ranked = ["combat", "dialogue"]
    labels = {"combat": "打斗/动作", "dialogue": "对话", "scenery": "景物", "psychology": "心理"}
    parts = []
    for k in ranked:
        for seg in (ex.get(k) or [])[:1]:  # 每类 1 段，控制上下文体量
            if seg.strip():
                parts.append(f"〔{labels[k]}·原著范例〕\n{seg.strip()}")
    block = ""
    if parts:
        block = ("\n\n# 同类场景·原著真实范例（照着这种句子节奏、用词密度、留白来写本章对应场景；"
                 "模仿语感，不要照抄情节）\n" + "\n\n".join(parts))

    # 笔法片段库(09)：按场景类型注入对应类的「风格卡要点 + 高分范例片段」;
    # 并对每章都补"章末钩子"范式(钩子是写作短板)。库为空时各自返回 None、自动跳过。
    try:
        from ..craft.pipeline import fewshot_block as _craft_fewshot
        _CRAFT_MAP = {"combat": "combat", "dialogue": "dialogue_subtext"}
        craft_parts = []
        for k in ranked:
            cat = _CRAFT_MAP.get(k)
            if cat:
                fb = _craft_fewshot(cat, n=2)
                if fb:
                    craft_parts.append(fb)
        hook_fb = _craft_fewshot("hook", n=1)
        if hook_fb:
            craft_parts.append(hook_fb)
        if craft_parts:
            block += ("\n\n# 本书笔法范式（来自「笔法拆解」库；按此句式/节奏/留白模仿，章末务必下钩子）\n"
                      + "\n\n".join(craft_parts))
    except Exception:  # noqa: BLE001 — 笔法库可选,失败不影响写作
        pass
    return block


def _writer_call(
    *,
    chapter_outline: dict,
    style_refs: list[dict],
    is_revision: bool,
    previous_attempt: dict | None,
    chapter_index: int,
    cached_blocks: list,
    prev_chapter_tail: str | None = None,
) -> tuple[str, float, int]:
    try:
        scene_exemplars = _scene_exemplar_block(chapter_outline)
    except Exception:  # noqa: BLE001
        scene_exemplars = ""
    user = build_writer_user_message(
        chapter_outline=chapter_outline,
        style_refs=style_refs,
        is_revision=is_revision,
        previous_attempt=previous_attempt,
        chapter_index=chapter_index,
        prev_chapter_tail=prev_chapter_tail,
        scene_exemplars=scene_exemplars,
    )
    # If this book has author-style mimic mode on, lead the writer with that
    # profile instead of the default 网文 voice.
    try:
        from ..style.pipeline import continuation_style_guide
        mimic_guide = continuation_style_guide()
    except Exception:
        mimic_guide = None
    writer_system = build_writer_system(mimic_guide)
    resp = llm.call(
        agent="draft.writer",
        model=MODEL_STRONG,
        system=[{"type": "text", "text": writer_system}, *cached_blocks],
        messages=[{"role": "user", "content": user}],
        # 16000：原著每章中位 5207 字，8000 token 顶不住 5000+ 字的成稿（会被截短）。
        max_tokens=16000,
        temperature=0.75,
    )
    return _strip_inline_markdown(resp.text or ""), resp.cost_usd, resp.elapsed_ms


def _reviewer_call(
    *,
    name: str,
    system_text: str,
    tool: dict,
    cached_blocks: list,
    chapter_outline: dict,
    prose: str,
    chapter_index: int,
) -> tuple[dict, float]:
    user = (
        f"# 第 {chapter_index} 章 · 待审\n\n"
        f"## 本章大纲\n{json.dumps(chapter_outline, ensure_ascii=False, indent=2)}\n\n"
        f"## 章节正文\n\n{prose}\n\n"
        "请按你的职责审查并调用工具返回结果。"
    )
    # 限流退避：审查撞 429/限流时退避重试，避免硬审"无结论"导致整章 blocked。
    # 之前正是因为这里一报错就被当成"零问题"放行，制造了大量假过审。
    import time as _time
    last_exc: Exception | None = None
    resp = None
    for _try in range(4):
        try:
            resp = llm.call(
                agent=f"draft.review.{name}",
                model=MODEL_FAST,
                system=[{"type": "text", "text": system_text}, *cached_blocks],
                messages=[{"role": "user", "content": user}],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                max_tokens=4000,
                temperature=0.2,
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            msg = str(exc)
            if any(k in msg for k in ("429", "RateLimit", "Quota", "rate limit", "TooManyRequests")):
                _time.sleep(20 * (_try + 1))  # 20s/40s/60s 渐进退避
                continue
            raise
    if resp is None:
        raise last_exc or RuntimeError("reviewer call failed")
    out = (resp.tool_use or {}).get("input", {}) or {}
    if not out and resp.text:
        out = _coerce_dict(resp.text)
    # Defensive: ensure 'issues' is a list of dicts.
    issues = out.get("issues", [])
    if isinstance(issues, str):
        try:
            issues = json.loads(issues)
        except json.JSONDecodeError:
            issues = []
    out["issues"] = [it for it in (issues or []) if isinstance(it, dict)]
    return out, resp.cost_usd


def _editor_call(
    *,
    reviews: dict[str, dict],
    chapter_index: int,
    attempt: int,
    max_attempts: int,
) -> tuple[dict, float]:
    user = (
        f"# 第 {chapter_index} 章 · 第 {attempt}/{max_attempts} 轮审查\n\n"
        f"## 三位审查员的输出\n\n"
        f"### 文风审查\n{json.dumps(reviews.get('style', {}), ensure_ascii=False, indent=2)}\n\n"
        f"### 剧情审查\n{json.dumps(reviews.get('plot', {}), ensure_ascii=False, indent=2)}\n\n"
        f"### 一致性审查\n{json.dumps(reviews.get('consistency', {}), ensure_ascii=False, indent=2)}\n\n"
        "请合并去重、做决策、（如需要）写 revision_brief，调用 decide_revision。"
    )
    try:
        resp = llm.call(
            agent="draft.editor",
            model=MODEL_FAST,
            system=EDITOR_SYSTEM,
            messages=[{"role": "user", "content": user}],
            tools=[EDITOR_TOOL],
            tool_choice={"type": "tool", "name": EDITOR_TOOL["name"]},
            max_tokens=4000,
            temperature=0.2,
        )
    except Exception:
        return heuristic_decision(reviews, attempt, max_attempts), 0.0

    out = (resp.tool_use or {}).get("input", {}) or {}
    if not out and resp.text:
        out = _coerce_dict(resp.text)
    if "decision" not in out or out.get("decision") not in {"approve", "revise", "ship_with_warnings"}:
        # Editor didn't return valid output — fall back to heuristic.
        out = heuristic_decision(reviews, attempt, max_attempts)
    return out, resp.cost_usd


def corpus_median_chapter_chars(default: int = 4000) -> int:
    """本书原著单章中位字数：按 corpus 章节真实 offset 统计（排除续写登记的 0-offset 章），
    并缓存到 style_profile.median_chapter_chars。作为 word_target 的**书本级默认值**——
    每本书自动算出自己的值（5000 字的书得 ~5000，8000 字的书得 ~8000），不写死。"""
    from ..memory.models import Chapter, StyleProfile
    with session_scope() as s:
        rows = s.execute(select(Chapter.char_offset_start, Chapter.char_offset_end)).all()
        lens = sorted((e - st) for st, e in rows
                      if st is not None and e is not None and e > st)
        med = int(lens[len(lens) // 2]) if lens else default
        sp = s.execute(select(StyleProfile).order_by(desc(StyleProfile.id)).limit(1)).scalars().first()
        if sp is not None and sp.median_chapter_chars != med:
            sp.median_chapter_chars = med  # 缓存/保存，供前端展示与复用
    return med


def write_chapter(
    *,
    outline_run_id: int,
    chapter_index: int,
    skip_reviews: bool = False,
    max_attempts: int = 3,
    reingest: bool = True,
    bilingual: bool = False,
    repo_commit: bool = False,
) -> dict[str, Any]:
    # 1) Load outline + chapter outline
    with session_scope() as s:
        run = s.get(OutlineRun, outline_run_id)
        if not run:
            raise ValueError(f"no OutlineRun id={outline_run_id}")
        chapters = list(run.chapters_json or [])
        chapter_outline = next(
            (c for c in chapters
             if isinstance(c, dict) and c.get("chapter_index") == chapter_index),
            None,
        )
        if not chapter_outline:
            raise ValueError(f"chapter {chapter_index} not in OutlineRun {outline_run_id}")
        # Determine the "after_chapter" for cached context — this is the
        # chapter PRIOR to the one we're writing.
        after_chapter = max(0, chapter_index - 1)

    # word_target 兜底：大纲未给则用**本书原著中位字数**（按书统计、非写死）。
    if not chapter_outline.get("word_target"):
        chapter_outline = {**chapter_outline, "word_target": corpus_median_chapter_chars()}

    # 2) Build cached context (entities/foreshadowings/mysteries/world rules etc.)
    ctx = _gather_context(after_chapter)
    cached_blocks = _ctx_blocks(ctx)

    # 3) Style references via FTS
    style_refs = _gather_style_refs(
        after_chapter=after_chapter,
        must_include=chapter_outline.get("must_include") or [],
    )

    # 3b) Serial continuity: tail of the previous generated chapter, if any.
    prev_tail = _prev_chapter_tail(outline_run_id, chapter_index)

    # 4) Create or reuse a ChapterDraft row.
    with session_scope() as s:
        existing = s.execute(
            select(ChapterDraft).where(
                ChapterDraft.outline_run_id == outline_run_id,
                ChapterDraft.chapter_index == chapter_index,
            ).limit(1)
        ).scalar_one_or_none()
        if existing:
            draft_id = existing.id
            existing.status = "writing"
            existing.attempts_json = []
            existing.cost_usd = 0.0
            existing.final_text = None
            existing.updated_at = datetime.utcnow()
        else:
            row = ChapterDraft(
                outline_run_id=outline_run_id,
                chapter_index=chapter_index,
                title=chapter_outline.get("title"),
                status="writing",
            )
            s.add(row)
            s.flush()
            draft_id = row.id

    attempts: list[dict] = []
    prev_attempt_feedback: dict | None = None
    total_cost = 0.0
    final_text = ""
    final_status = "approved"
    # Track the best attempt by *hard* (plot+consistency) issue score, so if we
    # ever fall through all attempts we keep the cleanest draft — not the last
    # one, which is usually the most over-revised.
    best_attempt: dict | None = None  # {"score": int, "prose": str, "attempt": int}

    def _flush_progress(stage: str) -> None:
        """Push current `attempts` + total_cost + a `stage` marker to the
        ChapterDraft row so a polling client can show fine-grained progress."""
        with session_scope() as s:
            d = s.get(ChapterDraft, draft_id)
            if d is None:
                return
            d.attempts_json = list(attempts)
            d.cost_usd = total_cost
            d.status = stage
            d.updated_at = datetime.utcnow()

    for attempt in range(1, max_attempts + 1):
        # Mark the attempt-in-progress so polling can show "Writer 写第 N 轮"
        attempt_record = {"attempt": attempt, "stage": "writer"}
        attempts.append(attempt_record)
        _flush_progress(f"attempt_{attempt}_writer")

        prose, w_cost, w_ms = _writer_call(
            chapter_outline=chapter_outline,
            style_refs=style_refs,
            is_revision=attempt > 1,
            previous_attempt=prev_attempt_feedback,
            chapter_index=chapter_index,
            cached_blocks=cached_blocks,
            prev_chapter_tail=prev_tail,
        )
        total_cost += w_cost
        attempt_record.update({
            "prose": prose,
            "writer_cost_usd": w_cost,
            "writer_elapsed_ms": w_ms,
            "stage": "writer_done",
        })
        _flush_progress(f"attempt_{attempt}_writer_done")

        if skip_reviews:
            attempt_record["reviews"] = None
            attempt_record["editor"] = {
                "decision": "approve",
                "rationale": "skip_reviews=true",
                "merged_issues": [],
            }
            attempt_record["stage"] = "done"
            final_text = prose
            final_status = "approved"
            break

        # Run 3 reviewers in parallel — IO bound, threadpool fits.
        attempt_record["stage"] = "reviewing"
        attempt_record["reviews"] = {}
        _flush_progress(f"attempt_{attempt}_reviewing")
        reviews: dict[str, dict] = {}
        review_jobs = [
            ("style", STYLE_REVIEWER_SYSTEM, STYLE_REVIEWER_TOOL),
            ("plot", PLOT_REVIEWER_SYSTEM, PLOT_REVIEWER_TOOL),
            ("consistency", CONSISTENCY_REVIEWER_SYSTEM, CONSISTENCY_REVIEWER_TOOL),
        ]
        # 第4审「时代语域」：默认关；仅当本书开启(era/culture 任一) 且 有语域卡 时加入。
        try:
            from ..style.pipeline import get_profile as _gp
            _prof = _gp() or {}
            _era_on = bool(_prof.get("era_check_enabled"))
            _cul_on = bool(_prof.get("culture_check_enabled"))
            _card = _prof.get("register_card")
            if (_era_on or _cul_on) and _card:
                review_jobs.append((
                    "era_register",
                    build_era_register_system(_card, _era_on, _cul_on),
                    ERA_REGISTER_REVIEWER_TOOL,
                ))
        except Exception:  # noqa: BLE001
            pass
        with ThreadPoolExecutor(max_workers=len(review_jobs)) as ex:
            futs = {
                ex.submit(
                    _reviewer_call,
                    name=name,
                    system_text=sys_text,
                    tool=tool,
                    cached_blocks=cached_blocks,
                    chapter_outline=chapter_outline,
                    prose=prose,
                    chapter_index=chapter_index,
                ): name
                for name, sys_text, tool in review_jobs
            }
            # As reviewers finish, update the row so UI shows lanes ticking off.
            for fut in futs:
                name = futs[fut]
                try:
                    out, c = fut.result()
                except Exception as exc:
                    out = {"issues": [], "overall": f"reviewer error: {exc}"}
                    c = 0.0
                reviews[name] = out
                total_cost += c
                attempt_record["reviews"] = dict(reviews)  # snapshot for poller
                _flush_progress(f"attempt_{attempt}_reviewing")

        attempt_record["reviews"] = reviews

        # Editor adjudicates
        attempt_record["stage"] = "editor"
        _flush_progress(f"attempt_{attempt}_editor")
        editor_out, e_cost = _editor_call(
            reviews=reviews,
            chapter_index=chapter_index,
            attempt=attempt,
            max_attempts=max_attempts,
        )
        total_cost += e_cost
        # Authoritative gate: only plot/consistency hard issues force a revise.
        # Style is advisory and never blocks (prevents the review death-spiral).
        gated = gate_decision(reviews, attempt, max_attempts)
        if editor_out.get("decision") != gated:
            editor_out["decision"] = gated
            editor_out.setdefault("rationale", "")
            editor_out["rationale"] = (editor_out["rationale"] + " | 门控覆盖：仅硬伤触发返工").strip(" |")
        attempt_record["editor"] = editor_out
        attempt_record["stage"] = "done"
        _flush_progress(f"attempt_{attempt}_done")

        # Remember the cleanest attempt seen so far.
        score = hard_issue_score(reviews)
        attempt_record["hard_score"] = score
        if best_attempt is None or score < best_attempt["score"]:
            best_attempt = {"score": score, "prose": prose, "attempt": attempt}

        decision = editor_out.get("decision")
        if decision in {"approve", "ship_with_warnings"}:
            final_text = prose
            final_status = decision
            break
        if decision == "blocked":
            # 硬审（剧情/一致性）无有效结论——多为持续限流。绝不假盖章 approve。
            # 保留正文供排查，但标 review_failed（不以 approv/ship 开头）→ 不计入完成、
            # 由编排器退避后重写/重审。这是修复"429 假过审"的下游闸门。
            final_text = prose  # 保留以便仅重审而非全重写
            final_status = "review_failed"
            editor_out.setdefault("rationale", "")
            editor_out["rationale"] = (
                editor_out["rationale"] + " | 硬审报错无结论，拒绝放行（review_failed）").strip(" |")
            attempt_record["editor"] = editor_out
            break

        # Set up next iteration's revision feedback
        merged = editor_out.get("merged_issues") or []
        failed = [i for i in merged if i.get("severity") in {"blocker", "major"}]
        prev_attempt_feedback = {
            "prose": prose,
            "revision_brief": editor_out.get("revision_brief", ""),
            "failed_issues_quoted": failed,
        }
    else:
        # Fell through all attempts: keep the cleanest draft, not the last.
        if best_attempt is not None:
            final_text = best_attempt["prose"]
        else:
            final_text = (attempts[-1]["prose"] if attempts else "")
        final_status = "shipped_with_warnings"

    # Persist
    with session_scope() as s:
        d = s.get(ChapterDraft, draft_id)
        d.attempts_json = attempts
        d.final_text = final_text
        d.cost_usd = total_cost
        d.status = final_status
        d.updated_at = datetime.utcnow()

    # A · 写→回灌记忆反馈环：把刚写好的章节增量抽取进记忆，让下一章"读到"它。
    # 后台线程，best-effort，绝不拖垮/阻断成稿返回。
    # success status is inconsistent across paths ("approved" / "approve" /
    # "ship_with_warnings" / "shipped_with_warnings") — match by prefix.
    _ok = bool(final_text) and str(final_status).startswith(("approv", "ship"))
    if reingest and _ok:
        # 修复 G1+G6(红蓝对抗·回归核查咬到 F5/自身):
        # G1 — 后台回灌走 threading.Thread,OS 线程**不继承 contextvar**,F5 的 book_scope 会丢失,
        #      切书后该章实体/FTS 会写进别的书。故捕获当前 slug,在线程体内重新 with book_scope(slug)。
        # G6 — 原 except: pass 把"记忆生长"失败静默吞掉(续写唯一的增量记忆通道),改为记录错误。
        import logging
        from contextlib import nullcontext
        from ..ingest.extract import extract_one_chapter
        from ..db import book_scope
        from ..books import library
        _slug = library.get_active()

        def _do_reingest():
            with (book_scope(_slug) if _slug else nullcontext()):
                extract_one_chapter(chapter_index, final_text)

        if repo_commit:
            # 接版本控制时**同步**回灌,确保增量 ch<N>.json 落盘后再 commit。
            try:
                _do_reingest()
            except Exception as exc:  # noqa: BLE001
                logging.getLogger(__name__).error("reingest(sync) ch%s 失败: %s", chapter_index, exc)
        else:
            def _reingest():
                try:
                    _do_reingest()
                except Exception as exc:  # noqa: BLE001
                    logging.getLogger(__name__).error("reingest(thread) ch%s 失败: %s", chapter_index, exc)
            try:
                import threading
                threading.Thread(target=_reingest, daemon=True).start()
            except Exception as exc:  # noqa: BLE001
                logging.getLogger(__name__).error("reingest 线程启动失败 ch%s: %s", chapter_index, exc)

    # 双语交织（接入主流程）：中文**真过审**后，把定稿锚定生成英文版（中英对照）。
    # 同步执行，确保返回时双语已就绪；非致命，失败不影响中文成稿。
    bilingual_status = None
    if bilingual and _ok:
        try:
            from ..style.bilingual import bilingual_from_zh
            br = bilingual_from_zh(final_text, chapter_index)
            bilingual_status = "done" if (br.get("final_en") or "").strip() else "empty"
            total_cost += br.get("cost_usd", 0.0)
        except Exception as e:  # noqa: BLE001
            bilingual_status = f"failed:{str(e)[:60]}"

    # B · 接版本控制：中文+英文+增量都就绪后，导出正文并 git commit 本章。
    repo_status = None
    if repo_commit and _ok:
        try:
            from ..repo import store as _repo
            r = _repo.snapshot_chapter(chapter_index)
            repo_status = "committed" if r.get("ok") else "nochange"
        except Exception as e:  # noqa: BLE001
            repo_status = f"failed:{str(e)[:60]}"

    return {
        "id": draft_id,
        "chapter_index": chapter_index,
        "status": final_status,
        "attempts": attempts,
        "final_text": final_text,
        "cost_usd": round(total_cost, 5),
        "bilingual": bilingual_status,
        "repo": repo_status,
    }


# ---------------------------------------------------------------------------
# Read APIs
# ---------------------------------------------------------------------------

def list_drafts(limit: int = 800) -> list[dict]:
    with session_scope() as s:
        rows = s.execute(
            select(ChapterDraft).order_by(desc(ChapterDraft.id)).limit(limit)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "outline_run_id": r.outline_run_id,
                "chapter_index": r.chapter_index,
                "title": r.title,
                "status": r.status,
                "n_attempts": len(r.attempts_json or []),
                # 正文字数（去空白）——让前端一眼看出空章/体量。
                "chars": len((r.final_text or "").replace(" ", "").replace("\n", "").replace("\t", "")),
                "cost_usd": r.cost_usd,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]


def get_draft(draft_id: int) -> dict | None:
    with session_scope() as s:
        r = s.get(ChapterDraft, draft_id)
        if not r:
            return None
        return {
            "id": r.id,
            "outline_run_id": r.outline_run_id,
            "chapter_index": r.chapter_index,
            "title": r.title,
            "status": r.status,
            "attempts": r.attempts_json or [],
            "final_text": r.final_text,
            "cost_usd": r.cost_usd,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }


def update_final_text(draft_id: int, text: str) -> bool:
    with session_scope() as s:
        r = s.get(ChapterDraft, draft_id)
        if not r:
            return False
        r.final_text = text
        r.status = "approved"
        r.updated_at = datetime.utcnow()
    return True
