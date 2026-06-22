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
                  skip_reviews: bool, reingest: bool) -> None:
    """后台入口：按计划逐章写 + 同步回灌，支持续写与分批。"""
    from ..db import session_scope
    from ..memory.models import BookWrite
    from ..draft import pipeline as draft
    from ..ingest.extract import extract_one_chapter

    try:
        plan, proj = _plan(projection_id)
        # 跳过已成稿（续写）
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
        cost = 0.0
        written = 0
        for rid, ci in todo:
            if max_chapters is not None and written >= max_chapters:
                _update(job_id, status="paused", stage=f"已写 {written} 章，分批暂停（可续）")
                return
            _update(job_id, current_chapter=ci, stage=f"成稿 第 {ci} 章")
            try:
                res = draft.write_chapter(outline_run_id=rid, chapter_index=ci,
                                          skip_reviews=skip_reviews, max_attempts=3,
                                          reingest=False)  # 批量内由本编排器同步回灌
                st = res.get("status"); cost += res.get("cost_usd", 0.0)
                ft = res.get("final_text") or ""
                ri = None
                if reingest and ft and str(st).startswith(("approv", "ship")):
                    _update(job_id, stage=f"回灌记忆 第 {ci} 章")
                    try:
                        ri = extract_one_chapter(ci, ft).get("status")
                    except Exception as e:  # noqa: BLE001
                        ri = f"reingest_failed:{str(e)[:60]}"
                log.append({"chapter": ci, "status": st, "attempts": len(res.get("attempts") or []), "reingest": ri})
            except Exception as e:  # noqa: BLE001 — 单章失败不终止整本，记录后继续
                log.append({"chapter": ci, "status": f"error:{str(e)[:80]}"})
            written += 1
            _update(job_id, chapters_done=already + written, log_json=list(log), cost_usd=round(cost, 5))

        _update(job_id, status="done", stage="全部章节完成", log_json=list(log), cost_usd=round(cost, 5))
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
                "log": r.log_json or [], "error": r.error, "cost_usd": r.cost_usd,
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
