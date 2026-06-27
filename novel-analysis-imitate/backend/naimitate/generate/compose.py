"""Phase 2+ · compose 虚拟书:生成产物的载体。

核心思路(复用现有生成内核、零重写):现有 draft.write_chapter 从 **active book 的
novel.db** 读 style_profile / 26 类笔法卡 / FTS 文风范文 / 实体世界。所以「用 A 的文风
写新故事」最干净的做法 = 把源书 A 的 book 目录**克隆**成一本虚拟书 → set_active → 给新
故事建 OutlineRun → write_chapter 即自动带上 A 的声音。

- UC2(A 文风写我的故事):克隆 A → voice=A。
- UC1(融合 N 书世界观+文风):克隆主源 → 叠加融合文风摘要写进 StyleProfile.notes。
- UC3(移植):克隆克苏鲁组主源(文风)→ 大纲承载从 A/B/C 抽象来的剧情母核(后续)。
"""
from __future__ import annotations

import shutil
from datetime import datetime

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from app.books import library  # noqa: E402
from app.db import session_scope, book_scope  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402
from . import _voice  # noqa: E402
from ..project import store as project_store  # noqa: E402

BOOKS_DIR = library.BOOKS_DIR


def create_from_source(cslug: str, source_slug: str, *, overwrite: bool = False,
                       mode: str = "voice_only") -> dict:
    """建虚拟书 cslug。

    - mode="voice_only"(默认,UC1-4 生成新故事用):**只**搬运源书的文风资产
      (StyleProfile 含 scene_exemplars + 26 类笔法卡),不带源书章节/实体/FTS —— 这样
      writer 有 A 的声音、却不会把 A 的剧情/人物当成续写内容写进来(避免内容污染)。
    - mode="full"(re-voice/续写 A 自身用):整库克隆。
    """
    src = BOOKS_DIR / source_slug
    if not src.is_dir():
        raise ValueError(f"source book {source_slug!r} not found")
    dst = BOOKS_DIR / cslug
    if dst.exists():
        if not overwrite:
            raise ValueError(f"compose book {cslug!r} already exists")
        shutil.rmtree(dst)

    if mode == "full":
        shutil.copytree(src, dst)
        return {"cslug": cslug, "mode": mode, "cloned_from": source_slug}

    # voice_only:建空书 → 复制文风资产
    dst.mkdir(parents=True, exist_ok=True)
    _copy_voice_assets(source_slug, cslug)
    return {"cslug": cslug, "mode": mode, "voice_from": source_slug}


def _copy_voice_assets(source_slug: str, cslug: str) -> None:
    """把源书的 StyleProfile(含 scene_exemplars/register)+ 笔法片段/卡复制到新书。"""
    from app.memory.models import StyleProfile, CraftSnippet, CraftStyleCard

    # 1) 读源(修复 G2:book_scope 进程级绑定,防并发切书把读/写落到错书)
    library.set_active(source_slug)
    with book_scope(source_slug):
        init_schema()
        with session_scope() as s:
            sp = s.query(StyleProfile).order_by(StyleProfile.id.desc()).first()
            sp_data = None
            if sp:
                sp_data = {c.name: getattr(sp, c.name) for c in StyleProfile.__table__.columns
                           if c.name != "id"}
            snippets = [{c.name: getattr(r, c.name) for c in CraftSnippet.__table__.columns if c.name != "id"}
                        for r in s.query(CraftSnippet).all()]
            cards = [{c.name: getattr(r, c.name) for c in CraftStyleCard.__table__.columns if c.name != "id"}
                     for r in s.query(CraftStyleCard).all()]

    # 2) 写新书
    library.set_active(cslug)
    with book_scope(cslug):
        init_schema()
        with session_scope() as s:
            if sp_data:
                sp_data["mimic_enabled"] = 1   # 生成新故事必开仿写
                s.add(StyleProfile(**sp_data))
            for d in snippets:
                s.add(CraftSnippet(**d))
            for d in cards:
                s.add(CraftStyleCard(**d))


def overlay_fused_voice(cslug: str, source_slugs: list[str]) -> dict:
    """UC1:把多本源书的文风摘要融合,写进虚拟书 StyleProfile 的 notes,
    作为 writer 的额外声音指引(主声音仍来自克隆源的完整 StyleProfile)。"""
    summary = _voice.fuse_style_summaries(source_slugs)
    library.set_active(cslug)
    from app.memory.models import StyleProfile
    with book_scope(cslug):   # 修复 G2
        init_schema()
        with session_scope() as s:
            row = s.query(StyleProfile).order_by(StyleProfile.id.desc()).first()
            if not row:
                row = StyleProfile()
                s.add(row)
            base = (row.summary or "")
            fused_note = f"\n\n【融合文风指引(取自 {', '.join(source_slugs)})】\n{summary}"
            row.summary = (base + fused_note)[:6000]
            row.mimic_enabled = 1   # 融合写作必须开启仿写
    return {"cslug": cslug, "fused_from": source_slugs, "summary_chars": len(summary)}


def seed_genome(cslug: str, source_slug: str) -> dict:
    """把源书的文风基因组 system-prompt 注入虚拟书 StyleProfile.summary,
    让 writer 用"分层范式 spec"而非"单段总结"仿写(基因组驱动生成)。"""
    from ..analysis import style_genome
    g = style_genome.get_genome(source_slug)
    spec = (g or {}).get("system_prompt") or ""
    if not spec:
        return {"cslug": cslug, "seeded_genome": False, "reason": "源书无基因组,先抽取"}
    library.set_active(cslug)
    from app.memory.models import StyleProfile
    with book_scope(cslug):   # 修复 G2
        init_schema()
        with session_scope() as s:
            row = s.query(StyleProfile).order_by(StyleProfile.id.desc()).first()
            if not row:
                row = StyleProfile(); s.add(row)
            row.mimic_enabled = 1
            # 基因组 spec 置于最前(优先级最高),保留原总结作补充
            base = row.summary or ""
            row.summary = (spec + "\n\n【附:原始文风总结】\n" + base)[:12000]
    return {"cslug": cslug, "seeded_genome": True, "spec_chars": len(spec)}


def export_chapters(cslug: str) -> dict:
    """导出该虚拟书已生成章节的 final_text 拼合。"""
    library.set_active(cslug)
    from app.memory.models import ChapterDraft
    with book_scope(cslug):   # 修复 G2
        init_schema()
        with session_scope() as s:
            rows = s.query(ChapterDraft).order_by(ChapterDraft.outline_run_id,
                                                  ChapterDraft.chapter_index).all()
            parts, meta = [], []
            for r in rows:
                if r.final_text:
                    parts.append(r.final_text)
                    meta.append({"chapter_index": r.chapter_index, "chars": len(r.final_text)})
    return {"cslug": cslug, "chapters": meta, "text": "\n\n".join(parts)}
