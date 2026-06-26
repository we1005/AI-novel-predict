"""基础抽取整合层:**直接复用主项目既有设施**(不重造)。

主项目 backend 早就有:6 个抽取 agent(实体/伏笔/状态/剧情点/世界规则/谜团)+ 关系图
(去重 / 关系抽取 / importance 重算)。本层只是把它们接进墨析编排器、全程 book_scope
串起来跑,并提供读取入口给前端(实体表 / 伏笔 / 剧情点 / 世界设定 / 关系网)。
"""
from __future__ import annotations

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from sqlalchemy import select, text as _sql  # noqa: E402
from app.db import get_engine, session_scope, book_scope  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402
from app.ingest import extract as ext  # noqa: E402  6 抽取 agent
from app.graph import dedup as dedup_pipe, relationships as rel_pipe, projections  # noqa: E402


def run_base(slug: str, *, batch: int = 50, do_graph: bool = True) -> dict:
    """对全书跑既有 6 抽取 agent(分批)+ 关系图(去重/关系/importance)。"""
    with book_scope(slug):
        init_schema()
        with get_engine().begin() as c:
            maxch = c.execute(_sql("SELECT MAX(chapter) FROM chapter_fts")).scalar() or 0
        if not maxch:
            return {"error": "无章节 — 先切分", "batches": 0}
        n_ok = 0
        starts = list(range(1, maxch + 1, batch))
        for st in starts:
            en = min(st + batch, maxch + 1)
            try:
                ext.run_batch(st, en, finalize=False)
                n_ok += 1
                print(f"[base] {slug} 抽取 {st}-{en-1} ok ({n_ok}/{len(starts)})", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[base] {slug} 抽取 {st}-{en-1} 失败: {str(e)[:100]}", flush=True)
        graph = {}
        if do_graph:
            try:
                graph["dedup"] = dedup_pipe.run()
            except Exception as e:  # noqa: BLE001
                print(f"[base] dedup 失败: {str(e)[:80]}", flush=True)
            try:
                graph["relationships"] = rel_pipe.extract(top_n=60).get("count") if isinstance(rel_pipe.extract(top_n=60), dict) else None
            except Exception as e:  # noqa: BLE001
                print(f"[base] 关系抽取 失败: {str(e)[:80]}", flush=True)
            try:
                graph["importance"] = projections.backfill_importance()
            except Exception as e:  # noqa: BLE001
                print(f"[base] importance 失败: {str(e)[:80]}", flush=True)
        # 统计
        with get_engine().begin() as c:
            counts = {t: c.execute(_sql(f"SELECT COUNT(*) FROM {t}")).scalar()
                      for t in ["entities", "relationships", "plot_points", "foreshadowings", "world_rules"]}
    return {"batches_ok": n_ok, "batches": len(starts), "counts": counts, "graph": graph}


def get_base(slug: str) -> dict:
    """读取既有抽取结果给前端:实体 / 关系网 / 剧情点 / 伏笔 / 世界设定。"""
    with book_scope(slug):
        init_schema()
        with get_engine().begin() as c:
            ents = [dict(r) for r in c.execute(_sql(
                "SELECT name,type,role,importance,description,first_appear_chapter "
                "FROM entities ORDER BY importance DESC LIMIT 60")).mappings()]
            plot = [dict(r) for r in c.execute(_sql(
                "SELECT chapter,importance,summary FROM plot_points ORDER BY chapter LIMIT 400")).mappings()]
            fore = [dict(r) for r in c.execute(_sql(
                "SELECT planted_chapter,resolved_chapter,status,type,description "
                "FROM foreshadowings ORDER BY planted_chapter LIMIT 300")).mappings()]
            world = [dict(r) for r in c.execute(_sql(
                "SELECT term,definition,first_chapter FROM world_rules ORDER BY first_chapter LIMIT 200")).mappings()]
        try:
            rels = rel_pipe.list_relationships()
        except Exception:
            rels = []
    return {"slug": slug, "entities": ents, "plot_points": plot,
            "foreshadowings": fore, "world_rules": world, "relationships": rels}
