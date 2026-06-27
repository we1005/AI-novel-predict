"""Phase 3 · 跨书融合产物(设计第四节)。

把一组同题材源书的世界观/文风/技法,用 MODEL_STRONG 蒸馏成可复用的「导演手册」,存进
project.db 的 fused_product 表:
- fused_worldview:N 书 world_rules + register → 共同母题 + 可融合设定骨架 + 冲突调和 + 术语表
- fused_style:N 书 StyleProfile.profile_json + scene_exemplars → 融合声音卡 + 跨书范文池
- fused_technique:N 书 technique_template 取并(数值取均、列表取并)→ 跨书技法模板

UC1 生成时把这三者塞进 compose 虚拟书(seed_compose_from_fusion)。
"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from sqlalchemy import select, text as _sql  # noqa: E402
from app.config import MODEL_STRONG  # noqa: E402
from app.db import session_scope, get_engine  # noqa: E402
from app.books import library  # noqa: E402
from app.llm import client as llm  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402
from ..project import store as project_store  # noqa: E402
from . import technique as tech  # noqa: E402


def _strip(s: str) -> str:
    return re.sub(r"```json|```", "", s or "").strip()


def _loads(resp) -> dict:
    try:
        from json_repair import repair_json
        d = json.loads(repair_json(_strip(resp.text)))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


# ---- 读取单本书的融合输入 ----

def _read_world(slug: str) -> dict:
    library.set_active(slug)
    init_schema()
    with get_engine().begin() as c:
        rules = c.execute(_sql("SELECT term, definition FROM world_rules ORDER BY first_chapter LIMIT 60")
                          ).mappings().all()
    from app.memory.models import StyleProfile
    with session_scope() as s:
        sp = s.query(StyleProfile).order_by(StyleProfile.id.desc()).first()
        register = (sp.register_card_json or {}) if sp else {}
        setting = ((sp.profile_json or {}).get("setting_register")) if sp else None
    return {"slug": slug, "rules": [dict(r) for r in rules],
            "register_card": register, "setting_register": setting}


def _exemplar_list(raw) -> list:
    """scene_exemplars 可能是 list 或 {scene_type: exemplar} dict;统一成 list。"""
    if isinstance(raw, dict):
        return list(raw.values())
    if isinstance(raw, list):
        return raw
    return []


def _read_style(slug: str) -> dict:
    library.set_active(slug)
    init_schema()
    from app.memory.models import StyleProfile
    with session_scope() as s:
        sp = s.query(StyleProfile).order_by(StyleProfile.id.desc()).first()
        if not sp:
            return {"slug": slug, "profile": {}, "exemplars": [], "summary": ""}
        pj = sp.profile_json or {}
        keep = {k: pj.get(k) for k in ("overall_voice", "sentence_rhythm", "register",
                                       "signature_vocabulary", "structural_habits",
                                       "narrative_pov") if pj.get(k) is not None}
        return {"slug": slug, "profile": keep,
                "exemplars": _exemplar_list(sp.scene_exemplars_json)[:3],
                "summary": sp.summary or ""}


# ---- 三个融合器 ----

def build_fused_worldview(project_slug: str, source_slugs: list[str]) -> dict:
    worlds = [_read_world(s) for s in source_slugs]
    payload = json.dumps(worlds, ensure_ascii=False)[:14000]
    sys = (
        "你是『世界观融合架构师』。下面是若干同题材小说的世界规则 + 语域设定。\n"
        "提炼出一个**可融合的统一世界观骨架**,输出 JSON:\n"
        "{common_motifs:[共同母题], fused_setting_skeleton:[融合后的设定骨架条目], "
        "conflict_reconciliation:[各书设定冲突项及调和方案], glossary:[{term,definition}], "
        "tone:基调一句话}。只输出 JSON。"
    )
    resp = llm.call(agent="analysis.worldview", model=MODEL_STRONG,
                    system=[{"type": "text", "text": sys}],
                    messages=[{"role": "user", "content": payload}],
                    max_tokens=3500, temperature=0.5, response_format={"type": "json_object"})
    card = _loads(resp)
    return project_store.save_fused(project_slug, "fused_worldview", card,
                                    source_slugs=source_slugs, cost_usd=resp.cost_usd or 0.0)


def build_fused_style(project_slug: str, source_slugs: list[str]) -> dict:
    styles = [_read_style(s) for s in source_slugs]
    exemplar_pool = []
    for st in styles:
        for ex in st["exemplars"]:
            exemplar_pool.append({"from": st["slug"], "exemplar": ex})
    payload = json.dumps([{"slug": s["slug"], "profile": s["profile"], "summary": s["summary"][:600]}
                          for s in styles], ensure_ascii=False)[:13000]
    sys = (
        "你是『文风融合声音导演』。下面是若干小说的文风画像。融合出一个**统一声音卡**,输出 JSON:\n"
        "{fused_voice:整体声音一句话, sentence_rhythm:句式节奏, register:语域, "
        "signature_devices:[可复用的标志性手法], shared_vocabulary:[共有高频意象/词], "
        "do:[该这样写], dont:[避免]}。只输出 JSON。"
    )
    resp = llm.call(agent="style.analyze", model=MODEL_STRONG,
                    system=[{"type": "text", "text": sys}],
                    messages=[{"role": "user", "content": payload}],
                    max_tokens=3000, temperature=0.5, response_format={"type": "json_object"})
    card = _loads(resp)
    # 修复 F7(红蓝对抗):键漂移检测。LLM 可能输出不同键名(尤其小米/非白名单模型 json_object 降级时),
    # seed_compose_from_fusion 按固定英文键死读会静默写 None。缺键即告警(不再无声),便于定位融合质量塌陷。
    _missing = [k for k in ("fused_voice", "sentence_rhythm", "register", "signature_devices",
                            "shared_vocabulary", "do", "dont") if not card.get(k)]
    if _missing:
        import logging
        logging.getLogger(__name__).warning(
            "build_fused_style(%s): 融合卡缺键 %s(键漂移/解析降级)→ seed 时该些维度将为空;建议重跑或换更强 STRONG 模型",
            project_slug, _missing)
    card["scene_exemplar_pool"] = exemplar_pool          # 跨书范文池(原文,供 writer few-shot)
    return project_store.save_fused(project_slug, "fused_style", card,
                                    source_slugs=source_slugs, cost_usd=resp.cost_usd or 0.0)


def build_fused_technique(project_slug: str, source_slugs: list[str]) -> dict:
    """各书 technique_template 取并:数值取均,列表取并(频次排序)。"""
    temps = []
    for s in source_slugs:
        t = tech.get_template(s) or tech.build_template(s)
        if t and not t.get("error"):
            temps.append(t)
    if not temps:
        return project_store.save_fused(project_slug, "fused_technique",
                                        {"error": "无可用单书模板"}, source_slugs=source_slugs)

    def _avg(path):
        vals = []
        for t in temps:
            v = t
            for k in path:
                v = (v or {}).get(k) if isinstance(v, dict) else None
            if isinstance(v, (int, float)):
                vals.append(v)
        return round(statistics.mean(vals), 1) if vals else None

    def _union(path, top=8):
        cnt = Counter()
        for t in temps:
            v = t
            for k in path:
                v = (v or {}).get(k) if isinstance(v, dict) else None
            if isinstance(v, list):
                cnt.update([str(x) for x in v])
        return [k for k, _ in cnt.most_common(top)]

    card = {
        "n_sources": len(temps),
        "rhythm": {
            "tension_avg": _avg(["rhythm", "tension_avg"]),
            "climax_interval_chapters": _avg(["rhythm", "climax_interval_chapters"]),
            "common_scene_rotation": _union(["rhythm", "scene_type_rotation"], 12),
        },
        "worldview_rule": {
            "infodump_ratio": _avg(["worldview_rule", "infodump_ratio"]),
            "front_loaded_ratio": _avg(["worldview_rule", "front_loaded_ratio"]),
            "preferred_methods": _union(["worldview_rule", "preferred_methods"], 4),
        },
        "pov_rule": {
            "nonprotagonist_pov_ratio": _avg(["pov_rule", "nonprotagonist_pov_ratio"]),
            "avg_away_span": _avg(["pov_rule", "avg_away_span"]),
        },
    }
    return project_store.save_fused(project_slug, "fused_technique", card, source_slugs=source_slugs)


def build_all(project_slug: str, source_slugs: list[str]) -> dict:
    return {
        "fused_worldview": build_fused_worldview(project_slug, source_slugs).get("card"),
        "fused_style": build_fused_style(project_slug, source_slugs).get("card"),
        "fused_technique": build_fused_technique(project_slug, source_slugs).get("card"),
    }


def get_fusion(project_slug: str) -> dict:
    out = {}
    for kind in ("fused_worldview", "fused_style", "fused_technique"):
        row = project_store.get_fused(project_slug, kind)
        out[kind] = row["card"] if row else None
    return out


# ---- 把融合产物塞进 compose 虚拟书(UC1 用)----

def seed_compose_from_fusion(cslug: str, project_slug: str) -> dict:
    """把 fused_style(声音卡+范文池)写进虚拟书 StyleProfile;fused_worldview 写进 world_rules + summary。"""
    fs = project_store.get_fused(project_slug, "fused_style")
    fw = project_store.get_fused(project_slug, "fused_worldview")
    library.set_active(cslug)
    init_schema()
    from app.memory.models import StyleProfile
    glossary_n = 0
    exemplars_added = 0
    with session_scope() as s:
        sp = s.query(StyleProfile).order_by(StyleProfile.id.desc()).first()
        if not sp:
            sp = StyleProfile(); s.add(sp)
        sp.mimic_enabled = 1
        notes = []
        if fs and fs.get("card"):
            c = fs["card"]
            notes.append("【融合声音】" + json.dumps(
                {k: c.get(k) for k in ("fused_voice", "sentence_rhythm", "register",
                                       "signature_devices", "shared_vocabulary", "do", "dont")},
                ensure_ascii=False))
            pool = c.get("scene_exemplar_pool") or []
            if pool:  # 跨书范文池注入 scene_exemplars(writer few-shot 会用)
                ex = list(sp.scene_exemplars_json or [])
                add = [p.get("exemplar") for p in pool if p.get("exemplar")][:6]
                ex.extend(add)
                sp.scene_exemplars_json = ex[:10]
                exemplars_added = len(add)
        if fw and fw.get("card"):
            c = fw["card"]
            gl = c.get("glossary") or []
            glossary_n = len(gl)
            # 融合世界观(含术语表)折进 summary 文本——voice_only 虚拟书无 chapters,
            # 不能写 world_rules(first_chapter 外键)。writer 经 continuation guide 读 summary。
            notes.append("【融合世界观】" + json.dumps(
                {k: c.get(k) for k in ("common_motifs", "fused_setting_skeleton",
                                       "conflict_reconciliation", "tone")}, ensure_ascii=False))
            if gl:
                terms = "；".join(f"{g.get('term')}={g.get('definition')}"
                                 for g in gl[:40] if isinstance(g, dict) and g.get("term"))
                notes.append("【融合世界观·术语表】" + terms[:3000])
        if notes:
            sp.summary = ((sp.summary or "") + "\n\n" + "\n\n".join(notes))[:9000]
    return {"cslug": cslug, "seeded_style": bool(fs), "seeded_worldview": bool(fw),
            "glossary_terms": glossary_n, "exemplars_added": exemplars_added}
