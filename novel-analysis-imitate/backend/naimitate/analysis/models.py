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


class WorldviewReveal(Base):
    """世界观/设定的『揭示事件』(江南式反信息倾倒铺垫的最小单元)。

    一章可有 0..N 条:某设定概念第一次被投喂给读者时,用什么手法、是否生硬倾倒、
    埋设到兑现隔了多远。聚合出『铺垫节奏卡』。
    """
    __tablename__ = "worldview_reveal"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter = Column(Integer, index=True)              # 出现章节号
    concept = Column(String)                           # 被揭示的设定/概念(如『序列体系』『真名』)
    reveal_method = Column(String)                     # 揭示手法:对话/情节体验/旁白直述/文献档案/回忆/环境暗示/角色独白
    is_infodump = Column(Integer, default=0)           # 是否信息倾倒(生硬大段解释)0/1
    setup_payoff_gap = Column(Integer, default=0)      # 埋设→兑现间隔章数(0=同章兑现/未知)
    importance = Column(Integer, default=50)           # 该设定对世界观的重要度 0-100
    excerpt = Column(Text)                             # 逐字依据(<=200字)
    summary = Column(Text)                             # 一句话:揭示了什么、怎么揭示
    created_at = Column(DateTime, default=datetime.utcnow)


class PovEvent(Base):
    """视角切换事件(POV 调度规则)。"""
    __tablename__ = "pov_event"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter = Column(Integer, index=True)              # 切到新视角的章节
    from_pov = Column(String)
    to_pov = Column(String)
    why_switch = Column(String)                        # 切换动机:制造悬念/补全信息/平行叙事/反派视角/情感铺垫
    return_after = Column(Integer, default=0)          # 几章后切回主视角(0=未切回/未知)
    summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class GoldenFingerStep(Base):
    """主角『金手指/外挂』升级台阶(升级斜率)。"""
    __tablename__ = "golden_finger_step"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter = Column(Integer, index=True)
    power_tier = Column(String)                        # 当前境界/层级名
    new_capability = Column(String)                    # 本台阶解锁的新能力
    trigger = Column(String)                           # 触发方式:奇遇/苦修/危机逼出/反派馈赠/血脉觉醒
    gap_vs_antagonist = Column(String)                 # 与当前主要对手的实力差:碾压/略胜/持平/落后/悬殊
    summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class RelationshipEvent(Base):
    """人物关系演变轨迹(关系状态的时间序列)。"""
    __tablename__ = "relationship_event"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter = Column(Integer, index=True)
    a = Column(String)                                 # 关系一方
    b = Column(String)                                 # 关系另一方
    state = Column(String)                             # 萍水/结盟/恋人/反目/背叛/忠贞/宿敌/师徒/亲情/竞争
    trigger = Column(Text)                             # 导致此状态的事件
    summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class SpeedReadStage(Base):
    """速读阶段:把全书按章序切成若干阶段(合并多章),重要阶段详写、次要一句带过。"""
    __tablename__ = "speed_read_stage"
    stage_index = Column(Integer, primary_key=True)
    chapter_start = Column(Integer)
    chapter_end = Column(Integer)
    title = Column(String)
    importance = Column(Integer, default=3)            # 1-5,越高越详
    peak_tension = Column(Integer, default=0)
    one_liner = Column(Text)                            # 一句话本阶段
    detail_json = Column(JSON)                          # 重要阶段才有:发生/铺垫/剧情/内心/互动/转折/线索
    created_at = Column(DateTime, default=datetime.utcnow)


class AnalysisCard(Base):
    """各分析层的聚合卡(per book,一类一行)。"""
    __tablename__ = "analysis_card"
    category = Column(String, primary_key=True)        # pacing / pov / golden_finger / relationship / worldview
    card_json = Column(JSON)
    cost_usd = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow)
