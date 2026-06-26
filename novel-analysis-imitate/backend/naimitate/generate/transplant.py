"""Phase 4 · UC3 剧情移植:A/B/C 剧情母核 → 重锚定到目标世界观 → 用其文风写。

两步:
1. extract_plot_cores:读源书高重要度 PlotPoint,用 MODEL_STRONG 抽象成**去设定**的
   剧情母核(剥离专有名词,只留冲突结构/人物功能/转折),得到可移植骨架。
2. uc3_transplant:克隆目标世界观的文风源 → 让模型把母核**重锚定**到目标世界观实体
   (如克苏鲁:序列/真名/古神)→ 落 OutlineRun → 复用 generate_chapter 生成。
"""
from __future__ import annotations

import json
import re

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from sqlalchemy import select  # noqa: E402
from app.config import MODEL_STRONG  # noqa: E402
from app.db import session_scope  # noqa: E402
from app.books import library  # noqa: E402
from app.llm import client as llm  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402
from app.memory.models import PlotPoint  # noqa: E402
from . import compose, usecases  # noqa: E402
from ..project import store as project_store  # noqa: E402


def _strip(s: str) -> str:
    return re.sub(r"```json|```", "", s or "").strip()


def _loads(resp, key: str) -> list:
    try:
        from json_repair import repair_json
        d = json.loads(repair_json(_strip(resp.text)))
    except Exception:
        return []
    if isinstance(d, dict) and isinstance(d.get(key), list):
        return d[key]
    if isinstance(d, list):
        return d
    return []


def extract_plot_cores(source_slug: str, *, top_n: int = 12) -> list[dict]:
    """读源书高重要度剧情点,抽象成去设定母核。返回 [{motif, conflict, function, turn}]。"""
    library.set_active(source_slug)
    init_schema()
    with session_scope() as s:
        pts = s.execute(select(PlotPoint).order_by(PlotPoint.importance.desc()).limit(top_n)
                        ).scalars().all()
        raw = [{"chapter": p.chapter, "summary": p.summary, "importance": p.importance} for p in pts]
    if not raw:
        return []
    body = "\n".join(f"- (ch{r['chapter']},重要度{r['importance']}) {r['summary']}" for r in raw)
    sys = (
        "你是『剧情母核抽象师』。下面是某小说的关键剧情点。把它们抽象成**去设定**的剧情母核:\n"
        "剥离一切专有名词(人名/地名/功法/组织),只保留冲突结构、人物功能(主角/导师/背叛者等)、\n"
        "情节转折。每条输出 {motif(母题一句), conflict(核心冲突), function(在故事中的功能), turn(转折点)}。\n"
        '只输出 JSON {"cores":[...]}。'
    )
    resp = llm.call(agent="analysis.beat", model=MODEL_STRONG,
                    system=[{"type": "text", "text": sys}],
                    messages=[{"role": "user", "content": body}],
                    max_tokens=3000, temperature=0.4,
                    response_format={"type": "json_object"})
    return _loads(resp, "cores")


def reanchor_to_world(cores: list[dict], anchor_world: str, *, n_chapters: int = 3) -> list[dict]:
    """把去设定母核重锚定到目标世界观,产出 n_chapters 章新故事大纲。"""
    sys = (
        "你是『剧情移植导演』。下面是一组去设定的剧情母核,以及目标世界观设定。\n"
        "把母核**重新落地**到目标世界观(用目标世界观的实体/规则替换抽象功能),\n"
        f"编成 {n_chapters} 章连贯新故事的逐章大纲。每章输出 "
        '{chapter_index, title, summary, beats:[...], must_include:[...]}。\n'
        '只输出 JSON {"chapters":[...]}。'
    )
    user = (f"# 目标世界观\n{anchor_world}\n\n# 去设定剧情母核\n"
            + json.dumps(cores, ensure_ascii=False, indent=2))
    resp = llm.call(agent="analysis.beat", model=MODEL_STRONG,
                    system=[{"type": "text", "text": sys}],
                    messages=[{"role": "user", "content": user}],
                    max_tokens=4000, temperature=0.6,
                    response_format={"type": "json_object"})
    return _loads(resp, "chapters")


def uc3_transplant(*, cslug: str, voice_source: str, plot_sources: list[str],
                   anchor_world: str, n_chapters: int = 3, top_n_per_source: int = 8,
                   project_slug: str = "", overwrite: bool = False) -> dict:
    """完整 UC3:抽取 plot_sources 的母核 → 重锚定到 anchor_world → 克隆 voice_source 文风 → 落 OutlineRun。"""
    cores: list[dict] = []
    for src in plot_sources:
        cores.extend(extract_plot_cores(src, top_n=top_n_per_source))
    chapters = reanchor_to_world(cores, anchor_world, n_chapters=n_chapters)
    if not chapters:
        return {"error": "重锚定失败(母核为空或模型未产出大纲)", "cores": len(cores)}
    compose.create_from_source(cslug, voice_source, overwrite=overwrite)
    usecases._ensure_mimic(cslug)
    run_id = usecases.make_outline_run(cslug, chapters, phase_name="UC3",
                                       user_hints=f"移植自{plot_sources},锚定:{anchor_world[:60]}")
    project_store.record_compose(cslug, project_slug=project_slug, use_case="uc3",
                                 source_slugs=list({voice_source, *plot_sources}),
                                 voice_source=voice_source, outline_run_id=run_id,
                                 meta={"n_cores": len(cores), "anchor_world": anchor_world[:200]})
    return {"cslug": cslug, "outline_run_id": run_id, "use_case": "uc3",
            "voice": voice_source, "n_cores": len(cores), "n_chapters": len(chapters)}
