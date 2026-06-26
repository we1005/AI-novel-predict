"""Phase 2.5 · technique_template 生产器(UC4 的「生产」端)。

从一本书已抽出的分析层(pacing/worldview/pov/golden 聚合卡 + 逐章 beat)蒸馏出一份
**可复用的导演手册**:节奏曲线规律、POV 调度规律、世界观铺垫规律、升级节律,以及一份
**逐章排布建议**(per_chapter:给新故事每章指定 scene_type/tension/pov/铺垫强度)。

存进该书 novel.db 的 analysis_card('technique')。UC4 取它 → inject_technique → 生成。
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from sqlalchemy import select  # noqa: E402
from app.db import session_scope  # noqa: E402
from app.books import library  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402
from ..analysis import models as M  # noqa: E402


def build_template(slug: str, *, n_chapters: int = 6) -> dict:
    """从分析层蒸馏 technique_template,并生成 n_chapters 章的逐章排布建议。"""
    library.set_active(slug)
    init_schema()
    with session_scope() as s:
        beats = s.execute(select(M.ChapterBeat).order_by(M.ChapterBeat.chapter)).scalars().all()
        cards = {c.category: c.card_json for c in
                 s.execute(select(M.AnalysisCard)).scalars().all()}
    if not beats:
        return {"error": "no beats — 先对该书跑分析层"}

    pacing = cards.get("pacing") or {}
    worldview = cards.get("worldview") or {}
    pov = cards.get("pov") or {}
    golden = cards.get("golden") or {}

    # —— 蒸馏规律 ——
    tens = [b.tension_level or 0 for b in beats]
    scene_seq = [b.scene_type for b in beats]
    # 高潮间隔:相邻"大高潮/张力>=85"章的平均距离
    climax_idx = [i for i, b in enumerate(beats)
                  if b.scene_type == "大高潮" or (b.tension_level or 0) >= 85]
    climax_gap = round(statistics.mean(
        [climax_idx[i + 1] - climax_idx[i] for i in range(len(climax_idx) - 1)]), 1
    ) if len(climax_idx) > 1 else None

    rhythm = {
        "tension_avg": round(statistics.mean(tens), 1) if tens else 0,
        "tension_range": [min(tens), max(tens)] if tens else [0, 0],
        "climax_interval_chapters": climax_gap,         # 大约每隔几章一个高潮
        "scene_type_rotation": _dominant_rotation(scene_seq),
        "opening_scene": scene_seq[0] if scene_seq else None,
    }
    pov_rule = {
        "nonprotagonist_pov_ratio": pov.get("nonprotagonist_pov_ratio"),
        "avg_away_span": pov.get("avg_away_span"),
        "switch_density": round((pov.get("switch_count") or 0) / max(1, len(beats)), 2),
    }
    worldview_rule = {
        "infodump_ratio": worldview.get("infodump_ratio"),
        "front_loaded_ratio": worldview.get("front_loaded_ratio"),
        "avg_setup_payoff_gap": worldview.get("avg_setup_payoff_gap"),
        "preferred_methods": _top_keys(worldview.get("reveal_method_distribution") or {}, 3),
    }
    golden_rule = {
        "avg_chapters_per_upgrade": golden.get("avg_chapters_per_upgrade"),
        "preferred_triggers": _top_keys(golden.get("trigger_distribution") or {}, 2),
    }

    # —— 逐章排布建议(把原著节奏的"形状"投射到 n_chapters 上)——
    per_chapter = _project_schedule(beats, n_chapters, rhythm, worldview_rule)

    template = {
        "source": slug,
        "rhythm": rhythm,
        "pov_rule": pov_rule,
        "worldview_rule": worldview_rule,
        "golden_rule": golden_rule,
        "per_chapter": per_chapter,
    }

    with session_scope() as s:
        row = s.get(M.AnalysisCard, "technique")
        if not row:
            row = M.AnalysisCard(category="technique")
            s.add(row)
        row.card_json = template
        row.updated_at = datetime.utcnow()
    return template


def get_template(slug: str) -> dict | None:
    library.set_active(slug)
    init_schema()
    with session_scope() as s:
        row = s.get(M.AnalysisCard, "technique")
        return row.card_json if row else None


def _dominant_rotation(seq: list[str]) -> list[str]:
    """取场景类型出现的主序(去连续重复),反映"铺垫→小高潮→喘息→大高潮"这类节律。"""
    out = []
    for x in seq:
        if not out or out[-1] != x:
            out.append(x)
    return out[:12]


def _top_keys(d: dict, n: int) -> list[str]:
    return [k for k, _ in sorted(d.items(), key=lambda kv: -kv[1])[:n]]


def _project_schedule(beats, n_chapters: int, rhythm: dict, worldview_rule: dict) -> dict:
    """把原著 N 章的张力/场景"形状"等比投射到目标 n_chapters 章,给每章一条排布建议。"""
    src = beats
    m = len(src)
    sched = {}
    front_load = (worldview_rule.get("front_loaded_ratio") or 0) >= 0.3
    for i in range(1, n_chapters + 1):
        # 等比映射到源章
        j = min(m - 1, round((i - 1) / max(1, n_chapters - 1) * (m - 1)))
        b = src[j]
        entry = {
            "scene_type": b.scene_type,
            "target_tension": b.tension_level,
            "pov": "主角" if b.is_protagonist_pov else "配角/反派",
            "hook": b.hook_type or "悬念",
        }
        # 前置铺垫:前 1/4 章若原著偏前载,提示加重世界观揭示
        if front_load and i <= max(1, n_chapters // 4):
            entry["worldview_emphasis"] = "加重设定揭示(原著为前载式铺垫)"
        sched[str(i)] = entry
    return sched
