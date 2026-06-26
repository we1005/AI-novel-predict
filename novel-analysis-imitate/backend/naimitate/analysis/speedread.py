"""速读模块:把全书按章序切成若干阶段 → 重要阶段详写、次要一句带过。

两步:
1. segment:读已抽好的逐章节拍(chapter_beat),MODEL_STRONG 一次切成 N 个阶段
   {title, chapter_start, chapter_end, importance(1-5), one_liner}。
2. detail:对 importance>=阈值 的阶段,读该段节拍 + 采样原文,MODEL_STRONG 详写
   {what_happened, foreshadowing, plot, character_inner, interactions, turns, threads}。

目标:让人最快摸清剧情走向/脉络/高潮节律/整体故事。
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from sqlalchemy import select, delete, text as _sql  # noqa: E402
from app.config import MODEL_STRONG  # noqa: E402
from app.db import get_engine, session_scope, book_scope  # noqa: E402
from app.books import library  # noqa: E402
from app.llm import client as llm  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402
from . import models as M  # noqa: E402


def _strip(s: str) -> str:
    return re.sub(r"```json|```", "", s or "").strip()


def _loads(resp, key: str):
    try:
        from json_repair import repair_json
        d = json.loads(repair_json(_strip(resp.text)))
    except Exception:
        return [] if key else {}
    if key:
        if isinstance(d, dict) and isinstance(d.get(key), list):
            return d[key]
        return d if isinstance(d, list) else []
    return d if isinstance(d, dict) else {}


def _beats(slug: str) -> list[dict]:
    with session_scope() as s:
        rows = s.execute(select(M.ChapterBeat).order_by(M.ChapterBeat.chapter)).scalars().all()
        return [{"chapter": r.chapter, "scene": r.scene_type, "tension": r.tension_level or 0,
                 "pov": r.pov_holder, "fn": r.plot_function, "summary": r.summary or ""} for r in rows]


def _chapter_text(chapter: int, head: int = 900, tail: int = 300) -> str:
    with get_engine().begin() as c:
        r = c.execute(_sql("SELECT body FROM chapter_fts WHERE chapter=:c"), {"c": chapter}).first()
    if not r or not r[0]:
        return ""
    b = r[0].strip()
    return b if len(b) <= head + tail else (b[:head] + "\n……\n" + b[-tail:])


# ---- 1. 切阶段 ----

def _num(v) -> int:
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else 0


def _segment_block(block: list[dict], n_stages: int) -> list[dict]:
    """对一段连续章节切 n_stages 个阶段。"""
    c0, c1 = block[0]["chapter"], block[-1]["chapter"]
    compact = "\n".join(f"{b['chapter']} [{b['scene']}|张力{b['tension']}] {b['summary']}" for b in block)
    sys = (
        f"你是中文小说的『速读编目员』。下面是第 {c0}~{c1} 章的逐章节拍(章号 [场景|张力] 摘要)。\n"
        f"把这 {c1-c0+1} 章按剧情自然断点切成 {n_stages} 个**连续不重叠**的阶段(合并多章)。\n"
        f"硬性要求:第一个阶段 chapter_start={c0},最后一个阶段 chapter_end={c1},"
        "中间各阶段首尾相接、不留空洞、不重叠、章号单调递增。\n"
        "- title:阶段小标题;importance 1-5(大高潮/重大转折=5,日常过渡=1-2);one_liner:一句话发生了什么。\n"
        '只输出 JSON {"stages":[{"title","chapter_start","chapter_end","importance","one_liner"}]}。'
    )
    resp = llm.call(agent="analysis.worldview", model=MODEL_STRONG,
                    system=[{"type": "text", "text": sys}],
                    messages=[{"role": "user", "content": compact[:120000]}],
                    max_tokens=4000, temperature=0.3, response_format={"type": "json_object"})
    out = []
    for st in _loads(resp, "stages"):
        if isinstance(st, dict) and _num(st.get("chapter_start")):
            out.append(st)
    return out


def segment(slug: str, *, target_stages: int = 24, block_chapters: int = 180) -> list[dict]:
    """分块切再拼接,保证覆盖到最后一章(避免模型一次切全书只切开头)。"""
    beats = _beats(slug)
    if not beats:
        return []
    bt = {b["chapter"]: b for b in beats}
    maxch = beats[-1]["chapter"]
    # 按章分块
    blocks = [beats[i:i + block_chapters] for i in range(0, len(beats), block_chapters)]
    per = max(3, round(target_stages / len(blocks)))
    raw = []
    for blk in blocks:
        try:
            raw.extend(_segment_block(blk, per))
        except Exception as e:  # noqa: BLE001
            print(f"[speedread] 块 {blk[0]['chapter']}-{blk[-1]['chapter']} 切分失败: {str(e)[:100]}", flush=True)
    # 规整:按 start 排序,end 兜底为下一段 start-1,保证全覆盖
    raw = [r for r in raw if _num(r.get("chapter_start"))]
    raw.sort(key=lambda r: _num(r.get("chapter_start")))
    out = []
    with session_scope() as s:
        s.execute(delete(M.SpeedReadStage))
        for i, st in enumerate(raw):
            cs = _num(st.get("chapter_start"))
            ce = _num(st.get("chapter_end")) or cs
            # 用下一段起点修正本段终点,消除空洞/重叠
            if i + 1 < len(raw):
                nxt = _num(raw[i + 1].get("chapter_start"))
                if nxt > cs:
                    ce = nxt - 1
            ce = min(max(ce, cs), maxch)
            peak = max((bt[c]["tension"] for c in range(cs, ce + 1) if c in bt), default=0)
            row = M.SpeedReadStage(
                stage_index=i + 1, chapter_start=cs, chapter_end=ce,
                title=(st.get("title") or f"阶段{i+1}")[:80],
                importance=max(1, min(5, int(_num(st.get("importance")) or 3))),
                peak_tension=peak, one_liner=(st.get("one_liner") or "")[:400],
                detail_json=None, created_at=datetime.utcnow())
            s.add(row)
            out.append({"stage_index": row.stage_index, "chapter_start": cs,
                        "chapter_end": ce, "importance": row.importance, "title": row.title})
    return out


# ---- 2. 详写重要阶段 ----

_DETAIL_SYS = (
    "你是中文小说的『剧情精读员』。给你某一阶段的逐章节拍 + 几章采样原文。\n"
    "请详细梳理本阶段,输出 JSON,字段:\n"
    "- what_happened:这一阶段按顺序发生了什么(可分点,3-6 条)。\n"
    "- plot:主线剧情推进了什么。\n"
    "- foreshadowing:埋了哪些伏笔 / 回收了哪些伏笔。\n"
    "- character_inner:主要人物内心/动机发生了什么变化。\n"
    "- interactions:关键人物互动 / 关系变化。\n"
    "- turns:本阶段的转折点 / 反转 / 高潮。\n"
    "- threads:本阶段在推进哪些长期线索。\n"
    "每个字段为字符串或字符串数组,简洁有信息量。只输出 JSON 对象。"
)


def detail_stage(slug: str, row: M.SpeedReadStage, beats: list[dict]) -> dict:
    seg = [b for b in beats if row.chapter_start <= b["chapter"] <= row.chapter_end]
    beat_block = "\n".join(f"{b['chapter']} [{b['scene']}] POV={b['pov']} {b['summary']}" for b in seg)
    # 采样原文:本阶段张力最高的最多 3 章
    top = sorted(seg, key=lambda b: -b["tension"])[:3]
    samples = "\n\n".join(f"【第{b['chapter']}章 原文摘录】\n{_chapter_text(b['chapter'])}" for b in top)
    user = f"# 阶段:{row.title}(第{row.chapter_start}-{row.chapter_end}章)\n\n# 逐章节拍\n{beat_block}\n\n# 采样原文\n{samples}"
    resp = llm.call(agent="analysis.worldview", model=MODEL_STRONG,
                    system=[{"type": "text", "text": _DETAIL_SYS}],
                    messages=[{"role": "user", "content": user[:60000]}],
                    max_tokens=3500, temperature=0.4, response_format={"type": "json_object"})
    return _loads(resp, "")


def run_speedread(slug: str, *, target_stages: int = 24, detail_threshold: int = 3) -> dict:
    """切阶段 + 详写重要阶段。全程 book_scope。"""
    with book_scope(slug):
        init_schema()
        stages = segment(slug, target_stages=target_stages)
        if not stages:
            return {"error": "无节拍数据 — 先跑节拍层", "stages": 0}
        beats = _beats(slug)
        detailed = 0
        with session_scope() as s:
            rows = s.execute(select(M.SpeedReadStage).order_by(M.SpeedReadStage.stage_index)).scalars().all()
            targets = [r for r in rows if (r.importance or 0) >= detail_threshold]
        for r in targets:
            try:
                dj = detail_stage(slug, r, beats)
            except Exception as e:  # noqa: BLE001
                print(f"[speedread] 阶段{r.stage_index} 详写失败: {str(e)[:100]}", flush=True)
                continue
            if dj:
                with session_scope() as s:
                    row = s.get(M.SpeedReadStage, r.stage_index)
                    row.detail_json = dj
                detailed += 1
            print(f"[speedread] {slug} 阶段{r.stage_index}/{len(rows)} 「{r.title}」详写完成", flush=True)
    return {"stages": len(stages), "detailed": detailed}


def get_speedread(slug: str) -> dict:
    with book_scope(slug):
        init_schema()
        with session_scope() as s:
            rows = s.execute(select(M.SpeedReadStage).order_by(M.SpeedReadStage.stage_index)).scalars().all()
            return {"slug": slug, "stages": [{
                "stage_index": r.stage_index, "chapter_start": r.chapter_start,
                "chapter_end": r.chapter_end, "title": r.title, "importance": r.importance,
                "peak_tension": r.peak_tension, "one_liner": r.one_liner, "detail": r.detail_json,
            } for r in rows]}
