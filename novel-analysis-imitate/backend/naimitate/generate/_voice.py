"""文风融合小工具:把多本源书的 StyleProfile.summary 汇成一段融合指引。

MVP 采用确定性拼接(带书名标签),零额外 LLM 成本;后续可换 MODEL_STRONG 蒸馏。
"""
from __future__ import annotations

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from app.books import library  # noqa: E402
from app.db import session_scope  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402


def _style_summary(slug: str) -> str:
    library.set_active(slug)
    init_schema()
    from app.memory.models import StyleProfile
    with session_scope() as s:
        row = s.query(StyleProfile).order_by(StyleProfile.id.desc()).first()
        return (row.summary if row and row.summary else "").strip()


def fuse_style_summaries(source_slugs: list[str]) -> str:
    parts = []
    for slug in source_slugs:
        try:
            sm = _style_summary(slug)
        except Exception:
            sm = ""
        if sm:
            parts.append(f"◆ {slug}:\n{sm[:1200]}")
    if not parts:
        return "(各源书尚无文风摘要,请先在续写项目里跑 /style 分析。)"
    return "\n\n".join(parts)
