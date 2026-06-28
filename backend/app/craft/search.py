"""统一的「风格素材检索」基座 —— push(编排器预取)与 agentic-pull(writer 运行时自取)共用。

设计意图(对应 agentic-search 议题 + "保留双轨可对比"):
- 检索逻辑只此一处,push 与 pull 都调它 → A/B 时唯一变量是"谁来决定查什么/何时查",而非检索实现本身。
- `search_corpus`:在原著章节正文(chapter_fts / BM25)按主题检索片段,**支持排除自产章**(防写到第 N 章
  时检索到自己刚生成的章 → 自我同质化;红蓝对抗"素材自我污染"风险)。
- `search_snippets`:在 craft 笔法库(CraftSnippet,按 category/subtype/tags/representativeness)过滤;
  库为空(当前各书 craft 未抽取)时优雅返回 []。
"""
from __future__ import annotations

import re

from sqlalchemy import select, text

from ..db import get_engine, session_scope
from ..memory.models import CraftSnippet

_NONCJK = re.compile(r"[^一-鿿A-Za-z0-9]+")


def _trigrams(q: str, cap: int = 15) -> list[str]:
    """FTS5 trigram 分词器只能匹配 ≥3 字的 query 项,故把每个连续中文/英数串切成
    滑动 3-gram。2 字概念词(建筑/码头)单独无法匹配,但自然短语的 3-gram 可命中。"""
    grams: list[str] = []
    for run in _NONCJK.split(q or ""):
        if len(run) >= 3:
            grams += [run[i:i + 3] for i in range(len(run) - 2)]
        # ≥3 字整词本身也是合法 3-gram 序列;<3 字串无法被 trigram 索引,跳过
    # 去重保序
    seen, out = set(), []
    for g in grams:
        if g not in seen:
            seen.add(g); out.append(g)
    return out[:cap]


def search_corpus(query: str, k: int = 5, *, exclude_chapters: set[int] | None = None,
                  before_chapter: int | None = None) -> list[dict]:
    """原著正文检索:返回 [{chapter, title, snip, score}]。
    中文 trigram 下整句 MATCH 易零召回,故先按关键词 OR 检索,零召回再退回整串。"""
    exclude = exclude_chapters or set()

    def _run(match: str) -> list[dict]:
        sql = ("SELECT chapter, title, snippet(chapter_fts, 2, '', '', '…', 40) AS snip, "
               "bm25(chapter_fts) AS score FROM chapter_fts WHERE chapter_fts MATCH :q ")
        params: dict = {"q": match}
        if before_chapter is not None:
            sql += "AND chapter < :bc "
            params["bc"] = before_chapter
        sql += "ORDER BY score LIMIT :n"
        params["n"] = k + len(exclude) + 5
        try:
            with get_engine().begin() as c:
                rows = [dict(r) for r in c.execute(text(sql), params).mappings().all()]
        except Exception:
            return []
        return [r for r in rows if r["chapter"] not in exclude][:k]

    grams = _trigrams(query)
    if not grams:
        return []
    return _run(" OR ".join(f'"{g}"' for g in grams))


def search_snippets(*, category: str | None = None, subtype: str | None = None,
                    tags: list[str] | None = None, min_rep: int = 0, k: int = 5) -> list[dict]:
    """craft 笔法库检索(库空则 [])。tags 命中任一即算匹配。"""
    with session_scope() as s:
        q = select(CraftSnippet)
        if category:
            q = q.where(CraftSnippet.category == category)
        if subtype:
            q = q.where(CraftSnippet.subtype == subtype)
        if min_rep:
            q = q.where(CraftSnippet.representativeness >= min_rep)
        rows = s.execute(q.order_by(CraftSnippet.representativeness.desc()).limit(k * 3)).scalars().all()
        out: list[dict] = []
        want = set(tags or [])
        for r in rows:
            rtags = r.tags_json if isinstance(r.tags_json, list) else []
            if want and not (want & set(rtags)):
                continue
            out.append({"category": r.category, "subtype": r.subtype, "chapter": r.chapter_number,
                        "excerpt": (r.excerpt or "")[:500],
                        "representativeness": r.representativeness, "tags": rtags})
            if len(out) >= k:
                break
        return out
