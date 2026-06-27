"""B · 滚动地平线整本书写作编排器.

把"能写一章"组合成"能写一本书"：按 projection 的逐-phase OutlineRun 顺序，
**逐章成稿 → 同步回灌记忆（A）→ 下一章**，让每一章都读得到前面新写章节的实体/伏笔/状态。

设计要点：
  - **单一事实源**：直接消费 RECONCILE 后 projection 落下的 per-phase OutlineRun，
    不另起一套大纲。
  - **同步回灌**：批量写作里 `write_chapter(reingest=False)` 后由本编排器**同步**调
    `extract_one_chapter`，保证下一章起草前记忆已更新（手动单章流仍用后台线程）。
  - **检查点/续跑**：每章一更新 job；已有"成功成稿"的章节自动跳过——重复调用即续写。
  - **分批**：`max_chapters` 让用户一次写 N 章、阶段 gate（人审）后再续。
"""

from __future__ import annotations

from typing import Any


_PHASE_REVIEW_SYSTEM = """你是长篇小说的"阶段责编"。给你某一阶段已写出的若干章正文片段，以及本阶段【计划要收束的伏笔】。
请做跨章 holistic 复审：连贯性、重复、伏笔燃尽、节奏/体量。

# 输出格式（严格）
只输出一个 JSON 对象，不要任何其它文字、不要 markdown 围栏：
{"continuity_issues": ["跨章断层/前后矛盾/时间线问题，没有则空数组"],
 "repetition": ["重复的场景/桥段/措辞，没有则空数组"],
 "foreshadow_resolved": [本阶段确实收束了的计划伏笔id],
 "foreshadow_missed": [本阶段计划收束但实际没交代的伏笔id],
 "pacing_note": "体量/节奏一句话评（赶/拖/合适）",
 "callback_suggestions": ["可加的前文回扣，没有则空数组"],
 "verdict": "pass 或 needs_work"}"""


def _phase_foreshadow_plan(run: dict) -> list[dict]:
    """该 phase 的 arc 计划收束伏笔 id + 描述。"""
    from ..db import session_scope
    from ..memory.models import ArcRun, Foreshadowing
    from sqlalchemy import select
    if run.get("source_kind") != "arc":
        return []
    ids: list[int] = []
    with session_scope() as s:
        arc = s.get(ArcRun, run.get("source_run_id"))
        if not arc:
            return []
        cands = arc.candidates_json if isinstance(arc.candidates_json, list) else []
        ci = run.get("source_chosen_index") or 0
        a = cands[ci] if 0 <= ci < len(cands) and isinstance(cands[ci], dict) else {}
        phases = a.get("phases") or []
        pi = run.get("phase_index") or 0
        ph = phases[pi] if 0 <= pi < len(phases) and isinstance(phases[pi], dict) else {}
        ids = [x for x in (ph.get("foreshadow_ids_addressed") or []) if isinstance(x, int)]
        if not ids:
            return []
        rows = s.execute(select(Foreshadowing).where(Foreshadowing.id.in_(ids))).scalars().all()
        return [{"id": r.id, "desc": (r.description or "")[:80], "status": r.status} for r in rows]


def review_phase(outline_run_id: int) -> dict:
    """阶段末跨章 holistic 复审 + 伏笔燃尽 + 体量评估（C）。"""
    import json
    import re
    from sqlalchemy import select
    from ..db import session_scope
    from ..memory.models import ChapterDraft
    from ..outline import pipeline as outline
    from ..llm import client as llm

    run = outline.get_run(outline_run_id)
    if not run:
        return {}
    chs = sorted(run.get("chapters") or [], key=lambda x: x.get("chapter_index", 0))
    # 取每章正文片段（头尾，控制上下文）
    snippets = []
    with session_scope() as s:
        for c in chs:
            ci = c.get("chapter_index")
            d = s.execute(select(ChapterDraft).where(
                ChapterDraft.outline_run_id == outline_run_id,
                ChapterDraft.chapter_index == ci).order_by(ChapterDraft.id.desc()).limit(1)).scalar_one_or_none()
            ft = (d.final_text if d else "") or ""
            if ft:
                head, tail = ft[:500], ft[-300:]
                snippets.append(f"【第{ci}章 {c.get('title','')}】\n{head}\n…（中略）…\n{tail}")
    if not snippets:
        return {"verdict": "skip", "note": "本阶段尚无成稿"}
    plan = _phase_foreshadow_plan(run)
    user = ("【本阶段计划收束的伏笔】\n" + json.dumps(plan, ensure_ascii=False)
            + "\n\n【本阶段已写章节正文片段】\n" + "\n\n".join(snippets))
    resp = llm.call(agent="bookwrite.phase_review", model="doubao-seed-2.0-code",
                    system=_PHASE_REVIEW_SYSTEM, messages=[{"role": "user", "content": user}],
                    max_tokens=4000, temperature=0.2)
    txt = re.sub(r"```json|```", "", resp.text or "").strip()
    try:
        out = json.loads(txt)
    except Exception:
        try:
            from json_repair import repair_json
            out = json.loads(repair_json(txt))
        except Exception:
            out = {"verdict": "unknown", "note": "复审解析失败"}
    out = out if isinstance(out, dict) else {}
    out["phase_name"] = run.get("phase_name")
    out["outline_run_id"] = outline_run_id
    out["chapters"] = [c.get("chapter_index") for c in chs]
    return out


_REPAIR_SYSTEM = """你是长篇小说的修订主编。给你某阶段的【复审意见】（连贯矛盾/重复/伏笔未收束/节奏体量）、该阶段【逐章大纲】、以及【计划却未收束的伏笔】。
请产出**针对具体章节的修订指令**——只挑真正需要改的章，把抽象问题落成可执行的"必含/必避"补充。

原则：
- 连贯矛盾 → 定位到出问题的那一章，给出"必须改成…"的明确指令。
- 伏笔未收束 → 选合适的章节，指令"在本章收束伏笔X：……"。
- 节奏偏赶/新悬念过密 → 对应章指令"放慢，先落地旧线，不要新引入Y"。
- 不要全改；最多挑 3-5 章，改在刀刃上。

# 输出格式（严格）
只输出一个 JSON 对象，不要任何其它文字、不要 markdown 围栏：
{"revisions": [
  {"chapter_index": 整数,
   "add_must_include": ["要补进本章的明确情节指令"],
   "add_must_avoid": ["本章要避免的（如：不再引入新悬念）"],
   "reason": "为什么改这章"}
]}"""


def repair_phase(outline_run_id: int, reingest: bool = True) -> dict:
    """针对阶段复审 needs_work，做一轮定向修补：诊断→补大纲指令→重写相关章→回灌→复审。"""
    import json
    import re
    from ..db import session_scope
    from ..outline import pipeline as outline
    from ..draft import pipeline as draft
    from ..ingest.extract import extract_one_chapter
    from ..llm import client as llm

    before = review_phase(outline_run_id)
    run = outline.get_run(outline_run_id)
    if not run:
        return {"error": "no outline run"}
    chs = run.get("chapters") or []
    plan = _phase_foreshadow_plan(run)
    missed_ids = set(before.get("foreshadow_missed") or [])
    missed = [p for p in plan if p["id"] in missed_ids]
    ch_brief = [{"chapter_index": c.get("chapter_index"), "title": c.get("title"),
                 "intent": (c.get("intent") or "")[:120],
                 "must_include": c.get("must_include") or [],
                 "foreshadow_ids_addressed": c.get("foreshadow_ids_addressed") or []} for c in chs]
    user = ("【复审意见】\n" + json.dumps({
        "continuity_issues": before.get("continuity_issues"),
        "repetition": before.get("repetition"),
        "pacing_note": before.get("pacing_note"),
        "foreshadow_missed": [{"id": m["id"], "desc": m["desc"]} for m in missed],
    }, ensure_ascii=False) + "\n\n【逐章大纲】\n" + json.dumps(ch_brief, ensure_ascii=False))
    resp = llm.call(agent="bookwrite.repair_diagnose", model="doubao-seed-2.0-code",
                    system=_REPAIR_SYSTEM, messages=[{"role": "user", "content": user}],
                    max_tokens=4000, temperature=0.3)
    txt = re.sub(r"```json|```", "", resp.text or "").strip()
    try:
        diag = json.loads(txt)
    except Exception:
        try:
            from json_repair import repair_json
            diag = json.loads(repair_json(txt))
        except Exception:
            diag = {}
    revisions = (diag.get("revisions") if isinstance(diag, dict) else None) or []

    applied = []
    by_idx = {c.get("chapter_index"): c for c in chs}
    for rv in revisions[:5]:
        ci = rv.get("chapter_index")
        cur = by_idx.get(ci)
        if not isinstance(ci, int) or not cur:
            continue
        # 把修订指令并进大纲（单一事实源），再重写该章
        new_must = list(cur.get("must_include") or []) + [str(x) for x in (rv.get("add_must_include") or [])]
        patch = {"must_include": new_must}
        avoid = [str(x) for x in (rv.get("add_must_avoid") or [])]
        if avoid:
            patch["must_avoid"] = list(cur.get("must_avoid") or []) + avoid
        outline.update_chapter(outline_run_id, ci, patch)
        try:
            res = draft.write_chapter(outline_run_id=outline_run_id, chapter_index=ci,
                                      skip_reviews=False, max_attempts=3, reingest=False)
            st = res.get("status")
            if reingest and (res.get("final_text") or "") and str(st).startswith(("approv", "ship")):
                try:
                    extract_one_chapter(ci, res["final_text"])
                except Exception as exc:  # 修复 G6:回灌失败不再静默吞(记忆生长通道)
                    import logging
                    logging.getLogger(__name__).error("bookwriter reingest ch%s 失败: %s", ci, exc)
            applied.append({"chapter": ci, "status": st, "reason": rv.get("reason")})
        except Exception as e:  # noqa: BLE001
            applied.append({"chapter": ci, "status": f"error:{str(e)[:60]}", "reason": rv.get("reason")})

    after = review_phase(outline_run_id)
    return {
        "outline_run_id": outline_run_id,
        "before_verdict": before.get("verdict"),
        "after_verdict": after.get("verdict"),
        "revisions_applied": applied,
        "before": before, "after": after,
    }


def _completed_chapter_set(outline_run_id: int) -> set[int]:
    """章节号集合：该 OutlineRun 下已成功成稿（approve/ship）的章节。"""
    from sqlalchemy import select
    from ..db import session_scope
    from ..memory.models import ChapterDraft
    done: set[int] = set()
    with session_scope() as s:
        rows = s.execute(select(ChapterDraft).where(
            ChapterDraft.outline_run_id == outline_run_id)).scalars().all()
        for r in rows:
            # status varies: approved/approve/ship_with_warnings/shipped_with_warnings
            if (r.final_text or "").strip() and str(r.status).startswith(("approv", "ship")):
                done.add(r.chapter_index)
    return done


def _plan(projection_id: int) -> tuple[list[tuple[int, int]], dict]:
    """展平成 [(outline_run_id, chapter_index), ...]，按 phase 顺序、章号递增。"""
    from ..arc import project as projection
    proj = projection.get_job(projection_id)
    if not proj:
        raise ValueError(f"no projection id={projection_id}")
    run_ids = proj.get("outline_run_ids") or []
    if not run_ids:
        raise ValueError("projection 没有 outline_run_ids（需先用 RECONCILE 后的推演重新生成）")
    from ..outline import pipeline as outline
    plan: list[tuple[int, int]] = []
    for rid in run_ids:
        run = outline.get_run(rid)
        if not run:
            continue
        for c in sorted(run.get("chapters") or [], key=lambda x: x.get("chapter_index", 0)):
            ci = c.get("chapter_index")
            if isinstance(ci, int):
                plan.append((rid, ci))
    return plan, proj


def create_job(projection_id: int) -> int:
    from datetime import datetime
    from ..db import session_scope
    from ..memory.models import BookWrite
    with session_scope() as s:
        row = BookWrite(projection_id=projection_id, status="writing", updated_at=datetime.utcnow())
        s.add(row); s.flush()
        return row.id


def _update(job_id: int, **fields) -> None:
    from datetime import datetime
    from ..db import session_scope
    from ..memory.models import BookWrite
    try:
        with session_scope() as s:
            row = s.get(BookWrite, job_id)
            if row:
                for k, v in fields.items():
                    setattr(row, k, v)
                row.updated_at = datetime.utcnow()
    except Exception:
        pass


def run_and_store(job_id: int, projection_id: int, max_chapters: int | None,
                  skip_reviews: bool, reingest: bool, max_phases: int | None = None,
                  bilingual: bool = False, repo_commit: bool = False) -> None:
    """后台入口：按计划逐章写 + 同步回灌，支持续写/分批/**阶段 gate**。

    每写完一个 phase（OutlineRun）就跑一次 `review_phase`（跨章 holistic 复审 +
    伏笔燃尽 + 体量）并入 `phase_reviews_json`；若设了 `max_phases`，写满 N 个阶段
    即暂停，等人审通过后再 resume（续跑自动跳过已成稿章节）。
    """
    from ..draft import pipeline as draft
    from ..ingest.extract import extract_one_chapter

    try:
        plan, proj = _plan(projection_id)
        done_by_run: dict[int, set[int]] = {}
        todo = []
        for rid, ci in plan:
            done = done_by_run.setdefault(rid, _completed_chapter_set(rid))
            if ci not in done:
                todo.append((rid, ci))
        total = len(plan)
        already = total - len(todo)
        _update(job_id, chapters_total=total, chapters_done=already)

        log: list[dict] = []
        reviews: list[dict] = []
        cost = 0.0
        written = 0
        phases_done = 0
        cur_phase = None

        def _finish_phase(rid: int):
            nonlocal phases_done
            # 缺口② 修补：阶段末跑一次图谱维护——新章节回灌进来的实体去重 + 重要度重算，
            # 防止名字变体裂开、重要度排序失真（影响下一阶段注入哪些上下文）。每阶段一次，省算力。
            _update(job_id, stage=f"阶段末图谱维护（去重+重要度）")
            try:
                from ..graph import dedup as _dedup
                from ..graph import projections as _proj
                _dedup.run(); _proj.backfill_importance()
            except Exception:  # noqa: BLE001
                pass
            _update(job_id, stage=f"阶段复审（OutlineRun {rid}）")
            try:
                rv = review_phase(rid)
            except Exception as e:  # noqa: BLE001
                rv = {"outline_run_id": rid, "verdict": "unknown", "note": str(e)[:80]}
            reviews.append(rv)
            phases_done += 1
            _update(job_id, phase_reviews_json=list(reviews))

        import time
        consecutive_fail = 0
        for rid, ci in todo:
            # 阶段边界：上一个 phase 写完 → 复审 + 检查 gate
            if cur_phase is not None and rid != cur_phase:
                _finish_phase(cur_phase)
                if max_phases is not None and phases_done >= max_phases:
                    _update(job_id, status="paused", stage=f"完成 {phases_done} 阶段，待人审（可续）")
                    return
            cur_phase = rid

            if max_chapters is not None and written >= max_chapters:
                _update(job_id, status="paused", stage=f"已写 {written} 章，分批暂停（可续）")
                return
            _update(job_id, current_chapter=ci, stage=f"成稿 第 {ci} 章")
            ok = False
            try:
                res = draft.write_chapter(outline_run_id=rid, chapter_index=ci,
                                          skip_reviews=skip_reviews, max_attempts=3,
                                          reingest=False, bilingual=bilingual)
                st = res.get("status"); cost += res.get("cost_usd", 0.0)
                ft = res.get("final_text") or ""
                ri = None
                if ft and str(st).startswith(("approv", "ship")):
                    ok = True
                    if reingest:
                        _update(job_id, stage=f"回灌记忆 第 {ci} 章")
                        try:
                            ri = extract_one_chapter(ci, ft).get("status")
                        except Exception as e:  # noqa: BLE001
                            ri = f"reingest_failed:{str(e)[:60]}"
                    # 回灌(落增量)之后再提交本章：正文+英文+增量一起进 git
                    if repo_commit:
                        try:
                            from ..repo import store as _repo
                            _repo.snapshot_chapter(ci)
                        except Exception:  # noqa: BLE001
                            pass
                log.append({"chapter": ci, "status": st, "attempts": len(res.get("attempts") or []), "reingest": ri})
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                log.append({"chapter": ci, "status": f"error:{msg[:80]}"})
                # 限流/额度：退避，给 RPM 冷却时间（不算入完成）
                if any(k in msg for k in ("429", "RateLimit", "Quota", "rate limit")):
                    time.sleep(45)
            # 只有真正成稿才计入完成；否则累计连续失败
            if ok:
                written += 1
                consecutive_fail = 0
            else:
                consecutive_fail += 1
            _update(job_id, chapters_done=already + written, log_json=list(log), cost_usd=round(cost, 5))
            # 连续多章失败（多半是 API 限流/额度）→ 暂停而非假装写完；resume 会重试这些章
            if consecutive_fail >= 3:
                _update(job_id, status="paused",
                        stage=f"连续 {consecutive_fail} 章失败（疑似 API 限流/额度），已暂停，恢复后可续")
                return
            time.sleep(2)  # 章间轻节流，避免突发请求撞 RPM 限流

        # 收尾：最后一个 phase 复审
        if cur_phase is not None:
            _finish_phase(cur_phase)
        _update(job_id, status="done", stage="全部章节完成", log_json=list(log),
                phase_reviews_json=list(reviews), cost_usd=round(cost, 5))
    except Exception as e:  # noqa: BLE001
        _update(job_id, status="failed", error=str(e)[:500])


def get_job(job_id: int) -> dict | None:
    from ..db import session_scope
    from ..memory.models import BookWrite
    with session_scope() as s:
        r = s.get(BookWrite, job_id)
        if not r:
            return None
        return {"id": r.id, "projection_id": r.projection_id, "status": r.status,
                "stage": r.stage or "", "chapters_total": r.chapters_total,
                "chapters_done": r.chapters_done, "current_chapter": r.current_chapter,
                "log": r.log_json or [], "phase_reviews": r.phase_reviews_json or [],
                "error": r.error, "cost_usd": r.cost_usd,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None}


def list_jobs(limit: int = 20) -> list[dict]:
    from sqlalchemy import select, desc
    from ..db import session_scope
    from ..memory.models import BookWrite
    with session_scope() as s:
        rows = s.execute(select(BookWrite).order_by(desc(BookWrite.id)).limit(limit)).scalars().all()
        return [{"id": r.id, "projection_id": r.projection_id, "status": r.status,
                 "stage": r.stage or "", "chapters_total": r.chapters_total,
                 "chapters_done": r.chapters_done, "cost_usd": r.cost_usd,
                 "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]
