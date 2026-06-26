"""文笔分析层:复用主项目 app/style(StyleProfile:声音/句式/语域/常用词汇/套路/范文)
+ app/craft(26 类笔法卡)。墨析只做读取 + 触发,全程 book_scope 防多进程串库。
"""
from __future__ import annotations

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from app.db import book_scope  # noqa: E402
from app.books import library  # noqa: E402
from app.style import pipeline as style_pipe  # noqa: E402
from app.craft import pipeline as craft_pipe  # noqa: E402


def run_style(slug: str, *, sample_n: int = 8) -> dict:
    """对一本书跑文笔分析(声音画像 + 范文 + 语域卡)。走 STRONG lane(小米)。"""
    with book_scope(slug):
        prof = style_pipe.analyze(sample_n=sample_n)
        try:
            style_pipe.extract_scene_exemplars(sample_n=min(6, sample_n))
        except Exception as e:  # noqa: BLE001
            print(f"[style] scene_exemplars 失败: {str(e)[:100]}", flush=True)
        try:
            style_pipe.extract_register_card(sample_n=sample_n)
        except Exception as e:  # noqa: BLE001
            print(f"[style] register_card 失败: {str(e)[:100]}", flush=True)
    return {"slug": slug, "ok": bool(prof)}


def get_style(slug: str) -> dict:
    """读取文笔画像 + 笔法卡,供前端「文笔」Tab 展示。"""
    with book_scope(slug):
        prof = style_pipe.get_profile()
        try:
            cards = craft_pipe.get_cards()
        except Exception:
            cards = []
        exemplars = _read_exemplars()
    p = (prof or {}).get("profile", {}) if prof else {}
    return {
        "slug": slug,
        "has_profile": bool(prof),
        "summary": (prof or {}).get("summary", ""),
        # 文笔画像各维度(主项目 StyleProfile.profile_json)
        "overall_voice": p.get("overall_voice"),
        "narrative_pov": p.get("narrative_pov"),
        "sentence_rhythm": p.get("sentence_rhythm"),
        "register": p.get("register"),
        "signature_vocabulary": p.get("signature_vocabulary"),   # 常用词汇/意象
        "tropes": p.get("tropes"),                                # 套路总结
        "structural_habits": p.get("structural_habits"),
        "narrative_structure": p.get("narrative_structure"),     # 故事架构
        "scene_styles": p.get("scene_styles"),
        "pitfalls_to_avoid": p.get("pitfalls_to_avoid"),
        "register_card": (prof or {}).get("register_card"),
        "scene_exemplars": exemplars,
        # 26 类笔法卡(写作技巧)
        "craft_cards": [{"category": c.get("category"),
                         "snippet_count": c.get("snippet_count"),
                         "card": c.get("card_json") or c.get("card")} for c in cards],
        "n_craft_cards": len(cards),
    }


def _read_exemplars() -> list:
    """在 book_scope 内读 scene_exemplars(list 或 {scene:text} dict 都兼容)。"""
    from app.memory.models import StyleProfile
    from app.db import session_scope
    try:
        with session_scope() as s:
            row = s.query(StyleProfile).order_by(StyleProfile.id.desc()).first()
            raw = row.scene_exemplars_json if row else None
    except Exception:
        raw = None
    if isinstance(raw, dict):
        return [{"scene": k, "text": v} for k, v in raw.items()]
    if isinstance(raw, list):
        return [{"scene": "", "text": x} if isinstance(x, str) else x for x in raw]
    return []
