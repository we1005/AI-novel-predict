"""Phase 1 · pov_event 分析层:视角调度时间轴。

不额外烧 LLM——直接复用 chapter_beat 已抽出的逐章 pov_holder / is_protagonist_pov,
在主视角与配角视角间的**切换点**生成 pov_event,并聚合 POV 调度规律
(切换次数、离开主视角的平均时长、配角视角占比)。
"""
from __future__ import annotations

from datetime import datetime

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from sqlalchemy import select, delete  # noqa: E402
from app.db import session_scope  # noqa: E402
from app.books import library  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402
from . import models as M  # noqa: E402


def derive_events(slug: str) -> dict:
    """从 chapter_beat 派生 pov_event(视角切换点)+ 聚合卡。需先跑 beat。"""
    library.set_active(slug)
    init_schema()
    with session_scope() as s:
        beats = s.execute(select(M.ChapterBeat).order_by(M.ChapterBeat.chapter)).scalars().all()
        if not beats:
            return {"error": "no beats — run analysis.beat first", "events": 0}
        s.execute(delete(M.PovEvent))
        seq = [(b.chapter, b.pov_holder or "?", b.is_protagonist_pov) for b in beats]
        events = []
        prev_pov = None
        leave_chapter = None      # 离开主视角的起点章
        switches = 0
        away_spans = []
        for i, (ch, pov, is_prot) in enumerate(seq):
            if prev_pov is not None and pov != prev_pov:
                switches += 1
                why = "回到主视角" if is_prot else "切到配角/反派视角"
                ev = M.PovEvent(chapter=ch, from_pov=prev_pov, to_pov=pov,
                                why_switch=why, return_after=0,
                                summary=f"第{ch}章视角由「{prev_pov}」切到「{pov}」",
                                created_at=datetime.utcnow())
                events.append(ev)
                # 统计离开主视角的连续跨度
                if not is_prot and leave_chapter is None:
                    leave_chapter = ch
                elif is_prot and leave_chapter is not None:
                    away_spans.append(ch - leave_chapter)
                    leave_chapter = None
            prev_pov = pov
        for ev in events:
            s.add(ev)
        n = len(seq)
        nonprot = sum(1 for _, _, ip in seq if not ip)
        # 回填 return_after:每个『切到配角』事件,到下一个『回到主视角』事件的章距
        prot_returns = [e.chapter for e in events if e.why_switch == "回到主视角"]
        for e in events:
            if e.why_switch != "回到主视角":
                nxt = next((c for c in prot_returns if c > e.chapter), None)
                e.return_after = (nxt - e.chapter) if nxt else 0
        card = {
            "n_chapters": n,
            "switch_count": switches,
            "nonprotagonist_pov_ratio": round(nonprot / n, 2) if n else 0,
            "avg_away_span": round(sum(away_spans) / len(away_spans), 1) if away_spans else 0,
            "distinct_pov_holders": len({pov for _, pov, _ in seq}),
        }
        row = s.get(M.AnalysisCard, "pov")
        if not row:
            row = M.AnalysisCard(category="pov")
            s.add(row)
        row.card_json = card
        row.updated_at = datetime.utcnow()
    return {"slug": slug, "events": len(events), "card": card}


def get_events(slug: str) -> dict:
    library.set_active(slug)
    init_schema()
    with session_scope() as s:
        rows = s.execute(select(M.PovEvent).order_by(M.PovEvent.chapter)).scalars().all()
        beats = s.execute(select(M.ChapterBeat).order_by(M.ChapterBeat.chapter)).scalars().all()
        card = s.get(M.AnalysisCard, "pov")
        return {
            "slug": slug,
            "events": [{"chapter": r.chapter, "from_pov": r.from_pov, "to_pov": r.to_pov,
                        "why_switch": r.why_switch, "return_after": r.return_after,
                        "summary": r.summary} for r in rows],
            "timeline": [{"chapter": b.chapter, "pov_holder": b.pov_holder,
                          "is_protagonist_pov": b.is_protagonist_pov} for b in beats],
            "pov_card": card.card_json if card else None,
        }
