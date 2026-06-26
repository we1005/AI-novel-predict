"""新分析层的 per-book 表,挂在现有 app.memory.models.Base 上。

导入本模块后再调用现有 `app.memory.schema_init.init_schema()`,create_all 会自动
在当前 active book 的 novel.db 里建这些表——**现有项目零改**。
"""
from __future__ import annotations

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from sqlalchemy import Column, Integer, String, Text, Float, JSON, DateTime  # noqa: E402
from datetime import datetime  # noqa: E402

from app.memory.models import Base  # noqa: E402  复用现有声明基类


class ChapterBeat(Base):
    """每章节拍表(节奏/结构时间轴的最小单元)。"""
    __tablename__ = "chapter_beat"
    chapter = Column(Integer, primary_key=True)        # 章节号(对齐 chapters.number)
    tension_level = Column(Integer)                    # 0-100 张力
    scene_type = Column(String)                        # 铺垫/小高潮/大高潮/热血/悬疑惊悚/煽情/日常/转场/其他
    pov_holder = Column(String)                        # 本章视角人物
    is_protagonist_pov = Column(Integer, default=1)    # 0/1
    plot_function = Column(String)                     # setup/escalation/payoff/twist/breather
    hook_type = Column(String)                         # 章末钩子类型
    cliffhanger_strength = Column(Integer, default=0)  # 0-100
    summary = Column(Text)                             # 一句话本章节拍
    created_at = Column(DateTime, default=datetime.utcnow)


class AnalysisCard(Base):
    """各分析层的聚合卡(per book,一类一行)。"""
    __tablename__ = "analysis_card"
    category = Column(String, primary_key=True)        # pacing / pov / golden_finger / relationship / worldview
    card_json = Column(JSON)
    cost_usd = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow)
