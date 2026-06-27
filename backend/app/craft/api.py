from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from . import pipeline
from ..books import library

router = APIRouter()


class ExtractReq(BaseModel):
    batch_size: int = 5
    max_chapters: int | None = None   # 调试用:只扫前 N 章;None=全书


@router.post("/extract")
def extract(req: ExtractReq | None = None, *, background: BackgroundTasks):
    """后台跑:逐批抽三类片段 → 逐类拆解风格卡。轮询 /craft/summary 看进度。"""
    bs = req.batch_size if req else 5
    mc = req.max_chapters if req else None
    # 修复 C8(红蓝对抗发现):在请求线程捕获当前激活书,传给后台任务并用 book_scope 锁定,
    # 否则用户启动抽取后立刻切书,后台线程会把笔法片段/风格卡写进新书的库(曾真实污染过)。
    slug = library.get_active()
    background.add_task(pipeline.extract_all, batch_size=bs, max_chapters=mc, slug=slug)
    return {"status": "started", "batch_size": bs, "max_chapters": mc,
            "msg": "笔法抽取已后台启动;完成后 /craft/summary 的 count 会增长、风格卡就绪"}


@router.post("/cards/rebuild")
def rebuild_cards():
    """仅重建风格卡(不重抽片段)。"""
    return pipeline.build_style_cards()


@router.get("/summary")
def summary():
    return pipeline.categories_summary()


@router.get("/snippets")
def snippets(category: str | None = None, limit: int = 500):
    return pipeline.list_snippets(category=category, limit=limit)


@router.get("/cards")
def cards():
    return pipeline.get_cards()
