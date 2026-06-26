"""文风基因组的公共取样器:按 scene_type / 张力 / plot_function 挑代表章并取原文。

所有基因组层(词汇/句式/修辞/氛围/场景套路/宏观架构)都从这里拿"有代表性的样本",
避免各层重复实现取样逻辑。依赖 chapter_beat(逐章节拍)定位典型章。
"""
from __future__ import annotations

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from sqlalchemy import select, text as _sql  # noqa: E402
from app.db import get_engine, session_scope  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402
from . import models as M  # noqa: E402


def chapter_text(chapter: int, head: int = 1600, tail: int = 500) -> str:
    with get_engine().begin() as c:
        r = c.execute(_sql("SELECT body FROM chapter_fts WHERE chapter=:c"), {"c": chapter}).first()
    if not r or not r[0]:
        return ""
    b = r[0].strip()
    return b if len(b) <= head + tail else (b[:head] + "\n……\n" + b[-tail:])


def all_beats() -> list[dict]:
    with session_scope() as s:
        rows = s.execute(select(M.ChapterBeat).order_by(M.ChapterBeat.chapter)).scalars().all()
        return [{"chapter": r.chapter, "scene": r.scene_type, "tension": r.tension_level or 0,
                 "pov": r.pov_holder, "is_prot": r.is_protagonist_pov, "fn": r.plot_function,
                 "hook": r.hook_type, "cliff": r.cliffhanger_strength or 0,
                 "summary": r.summary or ""} for r in rows]


def representative_chapters(scene_type: str, *, n: int = 4, beats: list[dict] | None = None) -> list[dict]:
    """某 scene_type 下最有代表性的 n 章(张力高=更典型),返回 [{chapter, ...beat}]。"""
    bs = beats if beats is not None else all_beats()
    seg = [b for b in bs if b["scene"] == scene_type]
    seg.sort(key=lambda b: -b["tension"])
    return seg[:n]


def sample_by_scene(*, per_type: int = 3, scene_types: list[str] | None = None) -> dict[str, list[dict]]:
    """每种 scene_type 取 per_type 个代表章(含原文片段),供场景套路/词汇/氛围层用。"""
    bs = all_beats()
    types = scene_types or sorted({b["scene"] for b in bs if b["scene"]})
    out: dict[str, list[dict]] = {}
    for t in types:
        reps = representative_chapters(t, n=per_type, beats=bs)
        out[t] = [{**r, "text": chapter_text(r["chapter"])} for r in reps]
    return out


def spread_sample(*, n: int = 12) -> list[dict]:
    """全书等距取 n 章(含原文),供词汇/句式/修辞这类"全局画像"层用,避免只看开头。"""
    bs = all_beats()
    if not bs:
        return []
    step = max(1, len(bs) // n)
    picked = bs[::step][:n]
    return [{**b, "text": chapter_text(b["chapter"])} for b in picked]


def high_tension_sample(*, n: int = 8) -> list[dict]:
    """张力最高的 n 章(含原文),供高潮/氛围/打斗套路层用。"""
    bs = sorted(all_beats(), key=lambda b: -b["tension"])[:n]
    bs.sort(key=lambda b: b["chapter"])
    return [{**b, "text": chapter_text(b["chapter"])} for b in bs]
