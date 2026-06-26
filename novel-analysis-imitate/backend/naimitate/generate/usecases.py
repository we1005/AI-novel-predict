"""Phase 2+ · 四类生成用例编排。

统一收敛到:**compose 虚拟书 → set_active → 建 OutlineRun(承载新故事逐章大纲)
→ draft.write_chapter**。差别只在「克隆谁的声音」「大纲承载什么剧情」。

- UC2 A文风写我的故事:克隆 A(声音)+ 用户给逐章大纲。
- UC1 融合N书世界观+文风:克隆主源 + overlay 融合文风 + 用户/推演大纲。
- UC4 江南技法注入:在任意 UC 基础上,把 technique_template(节奏/POV/铺垫)写进
  每章大纲的 directives,约束 writer(本文件提供 inject_technique)。
- UC3 移植:克隆克苏鲁组主源(声音)+ 大纲承载从 A/B/C 抽象的剧情母核(剧情母核
  抽取见 transplant.py;此处只负责落 OutlineRun + 生成)。
"""
from __future__ import annotations

from datetime import datetime

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from app.books import library  # noqa: E402
from app.db import session_scope  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402
from app.memory.models import OutlineRun  # noqa: E402
from . import compose  # noqa: E402
from ..project import store as project_store  # noqa: E402


def _normalize_chapters(chapters: list[dict]) -> list[dict]:
    """把用户给的逐章大纲规整成 write_chapter 认得的形状。"""
    out = []
    for i, ch in enumerate(chapters, start=1):
        idx = int(ch.get("chapter_index") or i)
        out.append({
            "chapter_index": idx,
            "title": ch.get("title") or f"第{idx}章",
            "summary": ch.get("summary") or ch.get("synopsis") or "",
            "beats": ch.get("beats") or [],
            "must_include": ch.get("must_include") or [],
            "word_target": ch.get("word_target") or None,
            "directives": ch.get("directives") or "",   # UC4 技法约束注入点
        })
    return out


def make_outline_run(cslug: str, chapters: list[dict], *,
                     phase_name: str = "compose", user_hints: str = "") -> int:
    """在虚拟书 cslug 的 DB 里建一个承载新故事的 OutlineRun,返回 run_id。"""
    library.set_active(cslug)
    init_schema()
    chs = _normalize_chapters(chapters)
    with session_scope() as s:
        run = OutlineRun(
            source_kind="compose", source_run_id=0, source_chosen_index=0,
            phase_index=0, phase_name=phase_name,
            chapter_start=chs[0]["chapter_index"], chapter_end=chs[-1]["chapter_index"],
            chapters_json=chs, user_hints=user_hints, cost_usd=0.0,
            created_at=datetime.utcnow())
        s.add(run)
        s.flush()
        run_id = run.id
    return run_id


def inject_technique(chapters: list[dict], template: dict) -> list[dict]:
    """UC4:把 technique_template(逐章 pacing/scene_type/pov 等)写进每章 directives。"""
    sched = (template or {}).get("per_chapter") or {}
    out = []
    for ch in chapters:
        idx = str(ch.get("chapter_index"))
        d = sched.get(idx) or {}
        if d:
            note = "；".join(f"{k}={v}" for k, v in d.items())
            ch = {**ch, "directives": (ch.get("directives", "") + " | 技法约束:" + note).strip(" |")}
        out.append(ch)
    return out


# ---- 四个用例的 setup(只建产物书 + OutlineRun;生成由 generate_chapter 触发)----

def uc2_voice_transfer(*, cslug: str, voice_source: str, chapters: list[dict],
                       project_slug: str = "", user_hints: str = "",
                       overwrite: bool = False) -> dict:
    """用 voice_source 的文风写用户给定剧情。"""
    compose.create_from_source(cslug, voice_source, overwrite=overwrite)
    _ensure_mimic(cslug)
    run_id = make_outline_run(cslug, chapters, phase_name="UC2", user_hints=user_hints)
    project_store.record_compose(cslug, project_slug=project_slug, use_case="uc2",
                                 source_slugs=[voice_source], voice_source=voice_source,
                                 outline_run_id=run_id)
    return {"cslug": cslug, "outline_run_id": run_id, "use_case": "uc2", "voice": voice_source}


def uc1_fused_world_voice(*, cslug: str, voice_source: str, fuse_sources: list[str],
                          chapters: list[dict], project_slug: str = "",
                          user_hints: str = "", overwrite: bool = False,
                          rebuild_fusion: bool = True) -> dict:
    """融合一组源书的**世界观骨架 + 文风声音**,写自创剧情。

    用 Phase 3 结构化融合产物:build fused_worldview/fused_style/fused_technique(MODEL_STRONG
    蒸馏)→ seed 进 compose 虚拟书(声音卡 + 跨书范文池 + 融合世界观术语)→ 生成。
    project_slug 留空时用 cslug 作为融合产物归属。
    """
    from . import fusion
    pslug = project_slug or f"_compose_{cslug}"
    sources = list(dict.fromkeys([voice_source, *fuse_sources]))   # 去重保序

    compose.create_from_source(cslug, voice_source, overwrite=overwrite)
    _ensure_mimic(cslug)

    # 1) 跨书融合产物(已存且不重建则复用)
    if rebuild_fusion or not project_store.get_fused(pslug, "fused_style"):
        fusion.build_fused_worldview(pslug, sources)
        fusion.build_fused_style(pslug, sources)
        fusion.build_fused_technique(pslug, sources)
    # 2) 塞进虚拟书
    seeded = fusion.seed_compose_from_fusion(cslug, pslug)

    run_id = make_outline_run(cslug, chapters, phase_name="UC1", user_hints=user_hints)
    project_store.record_compose(cslug, project_slug=pslug, use_case="uc1",
                                 source_slugs=sources, voice_source=voice_source,
                                 outline_run_id=run_id, meta={"fusion_project": pslug, **seeded})
    return {"cslug": cslug, "outline_run_id": run_id, "use_case": "uc1",
            "voice": voice_source, "fused": sources, "fusion_project": pslug, "seeded": seeded}


def uc4_technique_injected(*, cslug: str, voice_source: str, chapters: list[dict],
                           technique_template: dict | None = None,
                           technique_source: str = "", project_slug: str = "",
                           user_hints: str = "", overwrite: bool = False) -> dict:
    """江南式技法注入:在 voice_source 文风之上,按 technique_template 约束逐章节奏/POV/铺垫。

    technique_template 可直接给;也可只给 technique_source(从该书分析层**自动蒸馏**模板)。
    """
    from . import technique as tech
    if not technique_template:
        src = technique_source or voice_source
        technique_template = tech.build_template(src, n_chapters=len(chapters) or 6)
    compose.create_from_source(cslug, voice_source, overwrite=overwrite)
    _ensure_mimic(cslug)
    chs = inject_technique(chapters, technique_template)
    run_id = make_outline_run(cslug, chs, phase_name="UC4", user_hints=user_hints)
    project_store.record_compose(cslug, project_slug=project_slug, use_case="uc4",
                                 source_slugs=[voice_source], voice_source=voice_source,
                                 outline_run_id=run_id,
                                 meta={"technique_source": technique_source or voice_source})
    return {"cslug": cslug, "outline_run_id": run_id, "use_case": "uc4", "voice": voice_source,
            "technique": {k: technique_template.get(k) for k in ("rhythm", "pov_rule", "worldview_rule")}}


def _ensure_mimic(cslug: str) -> None:
    """克隆来的 StyleProfile 可能 mimic_enabled=0;生成前强制开启仿写。"""
    library.set_active(cslug)
    init_schema()
    from app.memory.models import StyleProfile
    with session_scope() as s:
        row = s.query(StyleProfile).order_by(StyleProfile.id.desc()).first()
        if row:
            row.mimic_enabled = 1


def generate_chapter(cslug: str, chapter_index: int, *, skip_reviews: bool = False) -> dict:
    """对虚拟书生成某章(复用现有 draft.write_chapter,自动带克隆来的文风/笔法)。

    全程 book_scope(cslug):异步生成期间即便前端切到别的书,本章也只写进 cslug 的库。
    """
    from app.db import book_scope
    rec = project_store.get_compose(cslug)
    if not rec or not rec.get("outline_run_id"):
        raise ValueError(f"compose book {cslug!r} has no outline_run — run a uc*_setup first")
    with book_scope(cslug):
        init_schema()
        from app.draft import pipeline as draft
        res = draft.write_chapter(outline_run_id=rec["outline_run_id"],
                                  chapter_index=chapter_index, skip_reviews=skip_reviews,
                                  reingest=False)   # 虚拟书不必回灌(避免污染 FTS 文风池)
    return {"cslug": cslug, "chapter_index": chapter_index,
            "chars": len((res or {}).get("final_text") or ""),
            "status": (res or {}).get("status")}
