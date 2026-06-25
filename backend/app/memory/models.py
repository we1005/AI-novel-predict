from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Chapter(Base):
    __tablename__ = "chapters"
    number = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    char_offset_start = Column(Integer, nullable=False)
    char_offset_end = Column(Integer, nullable=False)
    summary = Column(Text)


class Entity(Base):
    """人物 / 势力 / 物品 / 地点 / 功法 / 概念."""

    __tablename__ = "entities"
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String, nullable=False, index=True)  # person/faction/item/location/skill/concept
    name = Column(String, nullable=False, index=True)
    aliases_json = Column(JSON, default=list)
    first_appear_chapter = Column(Integer, ForeignKey("chapters.number"))
    description = Column(Text)
    importance = Column(Integer, default=0)  # 0-100, computed from mention count
    # Narrative role for `type=person`. Populated by the relationships LLM pass.
    # protagonist / antagonist / ally / supporting / minor / unknown
    role = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("type", "name", name="uq_entity_type_name"),)


class Relationship(Base):
    """A directional named relationship between two person entities.

    Two relationships in opposite directions can co-exist (e.g. A → B "师傅",
    B → A "弟子"). Multiple labels for the same direction collapse into one
    row: ``label`` carries a comma-joined or "/" -joined human label.
    """

    __tablename__ = "relationships"
    id = Column(Integer, primary_key=True, autoincrement=True)
    from_entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False, index=True)
    to_entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False, index=True)
    label = Column(String, nullable=False)  # short label e.g. "师徒"/"宿敌"/"恋人/同盟"
    description = Column(Text)
    first_chapter = Column(Integer)
    status = Column(String, default="active")  # active / ended
    weight = Column(Integer, default=1)  # narrative prominence
    __table_args__ = (
        UniqueConstraint("from_entity_id", "to_entity_id", "label", name="uq_rel_pair_label"),
    )


class EntityState(Base):
    """实体在某一章节的状态快照（境界/物品/关系等的 diff）."""

    __tablename__ = "entity_states"
    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False, index=True)
    chapter = Column(Integer, ForeignKey("chapters.number"), nullable=False, index=True)
    state_json = Column(JSON, nullable=False)  # 完整状态
    diff_json = Column(JSON)  # 相对上一次的 diff
    note = Column(Text)
    __table_args__ = (Index("ix_entity_state_chapter", "entity_id", "chapter"),)


class Foreshadowing(Base):
    """伏笔 — 创造力护栏的核心表."""

    __tablename__ = "foreshadowings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    planted_chapter = Column(Integer, ForeignKey("chapters.number"), nullable=False, index=True)
    planted_excerpt = Column(Text)
    description = Column(Text, nullable=False)
    type = Column(String, nullable=False)  # person/item/faction/mystery/promise/prophecy
    status = Column(String, nullable=False, default="open", index=True)  # open / resolved / dropped
    resolved_chapter = Column(Integer, ForeignKey("chapters.number"))
    resolved_description = Column(Text)
    related_entity_ids_json = Column(JSON, default=list)


class PlotPoint(Base):
    __tablename__ = "plot_points"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter = Column(Integer, ForeignKey("chapters.number"), nullable=False, index=True)
    summary = Column(Text, nullable=False)
    importance = Column(Integer, default=50)
    involved_entity_ids_json = Column(JSON, default=list)


class WorldRule(Base):
    __tablename__ = "world_rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    term = Column(String, nullable=False, unique=True)
    definition = Column(Text, nullable=False)
    first_chapter = Column(Integer, ForeignKey("chapters.number"))


class ExtractionBatch(Base):
    __tablename__ = "extraction_batches"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter_start = Column(Integer, nullable=False)
    chapter_end = Column(Integer, nullable=False)
    status = Column(String, default="pending", index=True)  # pending/running/done/failed
    cost_usd = Column(Float, default=0.0)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    __table_args__ = (UniqueConstraint("chapter_start", "chapter_end", name="uq_batch_range"),)


class LLMCall(Base):
    __tablename__ = "llm_calls"
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    agent = Column(String, index=True)
    model = Column(String)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cache_creation_tokens = Column(Integer, default=0)
    cache_read_tokens = Column(Integer, default=0)
    elapsed_ms = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    extra_json = Column(JSON)


class PredictionRun(Base):
    __tablename__ = "prediction_runs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    after_chapter = Column(Integer, nullable=False)
    candidates_json = Column(JSON)  # 阶段 A 输出
    scores_json = Column(JSON)  # 阶段 B 输出
    chosen_index = Column(Integer)
    written_text = Column(Text)  # 阶段 C 输出
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Mystery(Base):
    """A macro-level open question about the novel's worldview / plot.

    Distinct from ``Foreshadowing`` (which is per-chapter "did the author drop a
    hint that hasn't paid off yet"). A Mystery is "after reading the whole
    book, what genuine question is a thoughtful reader still asking?" — e.g.
    『主角真实身份是什么？』『XXX 王朝为何覆灭？』『世界魔力枯竭的真因？』

    Populated by an LLM pass that consumes the entire structured DB at once;
    individual extraction batches can't see this scale.
    """

    __tablename__ = "mysteries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(String, nullable=False)
    category = Column(String, index=True)  # identity / dynasty / worldview / mastermind / motive / prophecy / relationship / history
    severity = Column(String, default="major")  # core / major / minor
    why_it_matters = Column(Text)
    clues_json = Column(JSON, default=list)  # list of strings: chapter-anchored hints
    related_entity_ids_json = Column(JSON, default=list)
    related_foreshadow_ids_json = Column(JSON, default=list)
    source = Column(String, default="auto")  # auto / manual
    note = Column(Text)  # user's notes / hypotheses
    created_at = Column(DateTime, default=datetime.utcnow)

    # ----- lifecycle (per-batch incremental) -----
    status = Column(String, default="open", index=True)
    # open / sharpened / partially_resolved / resolved / contradicted
    confidence = Column(Integer, default=50)
    # 0-100. Bumped each time a later batch reinforces this question with a new
    # clue. UI hides confidence < 50 by default to suppress early-batch noise.
    first_seen_batch_id = Column(Integer)
    last_updated_batch_id = Column(Integer)
    last_updated_chapter = Column(Integer)
    updates_log_json = Column(JSON, default=list)
    # [{batch_id, chapter_range, change, summary, ...}]


class CharacterProfile(Base):
    """Per-character actor profile for the simulation pipeline.

    Built once (per character) by ProfileBuilder from the structured data
    we already extract: entity_states / relationships / foreshadows that
    involve this character. ``last_built_chapter`` records which chapter's
    state was used so we can re-build when the snapshot drifts too far from
    the simulator's current ``after_chapter``.
    """

    __tablename__ = "character_profiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Integer, ForeignKey("entities.id"), unique=True, nullable=False)
    bio = Column(Text)
    desires = Column(JSON, default=list)            # ["..."]
    fears = Column(JSON, default=list)              # ["..."]
    moral_compass = Column(Text)
    voice_style = Column(Text)                      # 说话风格、口头禅
    typical_actions = Column(JSON, default=list)    # ["..."]
    relationships_summary = Column(JSON, default=list)  # [{name, label, attitude}]
    secrets_known = Column(JSON, default=list)      # [{secret, learned_chapter}]
    secrets_hidden = Column(JSON, default=list)     # 自己藏的秘密
    arc_so_far = Column(Text)                       # 截至当前章节的成长轨迹概括
    last_built_chapter = Column(Integer)            # 这份档案是基于哪一章数据建的
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    after_chapter = Column(Integer, nullable=False)
    n_rounds = Column(Integer)
    n_characters = Column(Integer)
    focus_characters = Column(JSON, default=list)   # [entity_id, ...]
    user_hints = Column(Text)
    rounds_json = Column(JSON, default=list)
    # Each round: {round, actions: [{char_id, kind, target_id, content, reasoning}], state_snapshot}
    final_text = Column(Text)
    chapter_draft_id = Column(Integer)
    cost_usd = Column(Float, default=0.0)
    status = Column(String, default="pending", index=True)
    # pending / simulating / reporting / done / failed
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class InterviewLog(Base):
    """One question/answer pair against a character."""

    __tablename__ = "interview_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(Integer, ForeignKey("entities.id"), index=True)
    after_chapter = Column(Integer)
    question = Column(Text)
    answer = Column(Text)
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class OutlineRun(Base):
    """Per-phase chapter-by-chapter outline derived from an arc/predict winner.

    `chapters_json` is an array of chapter outlines: each chapter has its own
    intent / must_include / must_avoid / pacing / word_target etc. so the
    WriterAgent has a concrete prompt to follow.
    """

    __tablename__ = "outline_runs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_kind = Column(String)            # "arc" | "predict"
    source_run_id = Column(Integer)
    source_chosen_index = Column(Integer)
    phase_index = Column(Integer)
    phase_name = Column(String)
    chapter_start = Column(Integer)
    chapter_end = Column(Integer)
    chapters_json = Column(JSON, default=list)
    user_hints = Column(Text)
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChapterDraft(Base):
    """One chapter's prose draft + review history.

    `attempts_json` keeps every Writer/Reviewer/Editor pass so the UI can show
    how the chapter evolved across the ReAct loop. `final_text` is the version
    the user chose to ship.
    """

    __tablename__ = "chapter_drafts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    outline_run_id = Column(Integer, ForeignKey("outline_runs.id"))
    chapter_index = Column(Integer, index=True)
    title = Column(String)
    status = Column(String, default="draft")
    # draft / writing / reviewing / approved / shipped_with_warnings / failed
    attempts_json = Column(JSON, default=list)
    final_text = Column(Text)
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ArcRun(Base):
    """Whole-story arc prediction (macro-level outline, no prose).

    Distinct from PredictionRun (which is next-1-3-chapter, chapter-level
    expansion). Output schema is much richer: phased arcs with foreshadow
    coverage, hero-arc deltas, climax/ending shape.
    """

    __tablename__ = "arc_runs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    after_chapter = Column(Integer, nullable=False)
    target_chapters = Column(Integer)  # how many chapters of arc the user asked for
    user_hints = Column(Text)  # user's stylistic/tonal preferences for this run
    candidates_json = Column(JSON)
    scores_json = Column(JSON)
    chosen_index = Column(Integer)
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class StyleProfile(Base):
    """Per-book author writing-style analysis (opt-in, token-heavy).

    One row per book (latest analysis wins). ``profile_json`` holds the
    structured style breakdown (voice, scene-type styles, tropes, vocabulary,
    POV, pacing, setting/register, and a synthesized 续写指导). ``mimic_enabled``
    is the switch: when true, continuation should imitate this author's style
    instead of the default punchy-网文 voice. ``bilingual`` marks Western-setting
    books that should get the dual ZH/EN cross-translation continuation.
    """

    __tablename__ = "style_profile"
    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_json = Column(JSON)            # structured analysis
    summary = Column(Text)                 # short human-readable digest
    sampled_chapters = Column(JSON, default=list)
    mimic_enabled = Column(Integer, default=0)   # 0/1 — mimic author voice in续写
    bilingual = Column(Integer, default=0)       # 0/1 — dual ZH/EN continuation
    # 本书原著单章中位字数（从 corpus 统计得出，按书而异）——续写 word_target 的书本级默认值。
    median_chapter_chars = Column(Integer)
    # 各场景类型的原著真实范例段落 {combat:[...], dialogue:[...], scenery:[...], psychology:[...]}
    # ——写某类场景时作为 few-shot 范文注入 writer，让它照着原作语感写（"给范文"而非只"讲道理"）。
    scene_exemplars_json = Column(JSON)
    # 世界观语域卡：技术/年代基准 + 各阵营文化语域，供「时代语域」第4审逐元素归属判定。
    register_card_json = Column(JSON)
    era_check_enabled = Column(Integer, default=0)      # 时代错置层（universal，对所有阵营一视同仁）
    culture_check_enabled = Column(Integer, default=0)  # 阵营文化语域层（按词的归属角色判）
    model = Column(String)
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class EditSuggestion(Base):
    """一条润色建议（局部就地替换）。落库以便刷新后仍在 + 审计 + 纳入版本控制。

    锚点失效检测：base_hash 记录生成时中文定稿的哈希；展示/应用时若 quote 在**当前**
    正文里找不到（原文被改过），该条标 stale、禁止应用——避免错位乱改。
    """
    __tablename__ = "edit_suggestions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    draft_id = Column(Integer, index=True)
    chapter_index = Column(Integer, index=True)
    batch_id = Column(String, index=True)      # 一次生成run分组
    base_hash = Column(String)                 # 生成时 final_text 的哈希
    quote = Column(Text)
    replacement = Column(Text)
    category = Column(String)
    reason = Column(String)
    # pending | accepted | applied | rejected | stale | superseded
    status = Column(String, default="pending", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class BilingualDraft(Base):
    """A bilingual (ZH/EN) cross-translated continuation chapter.

    Produced by the STYLE-3 pipeline: independent ZH(mimic) + EN(native) drafts
    → cross-translate → merge. Holds both final versions plus intermediates.
    """

    __tablename__ = "bilingual_draft"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter = Column(Integer)
    brief = Column(Text)
    status = Column(String, default="writing")  # writing / done / failed
    stage = Column(String, default="")  # granular progress: zh_draft/en_recreate/translate/merge/done
    final_zh = Column(Text)
    final_en = Column(Text)
    drafts_json = Column(JSON)   # intermediates: zh_orig/en_orig/en_from_zh/zh_from_en
    error = Column(Text)
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class RevoiceJob(Base):
    """A 推翻文笔保留主干剧情 (re-voice) job: skeleton + rewrite in a target voice."""

    __tablename__ = "revoice_job"
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_chapter = Column(Integer)   # source chapter number (if from book), else null
    voice = Column(String)             # wangwen / mimic / english
    status = Column(String, default="writing")
    skeleton_json = Column(JSON)
    rewritten = Column(Text)
    error = Column(Text)
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class StoryProjection(Base):
    """A whole-book story projection: expand every phase of a chosen story arc
    into a continuous chapter-level outline covering current+1 → estimated end,
    plus a completeness verdict (are all core_truths revealed / foreshadowings
    resolved). Append-only."""

    __tablename__ = "story_projection"
    id = Column(Integer, primary_key=True, autoincrement=True)
    arc_run_id = Column(Integer)
    chosen_index = Column(Integer)
    after_chapter = Column(Integer)
    end_chapter = Column(Integer)
    total_chapters = Column(Integer)   # projected chapters generated
    status = Column(String, default="projecting")  # projecting / done / failed
    stage = Column(String, default="")             # granular progress
    arc_title = Column(String)
    phases_json = Column(JSON)          # sanitized phase plan
    chapters_json = Column(JSON)        # aggregated, re-anchored full outline
    outline_run_ids = Column(JSON)      # per-phase OutlineRun ids (draftable units)
    verdict_json = Column(JSON)         # completeness 裁决
    error = Column(Text)
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class BookWrite(Base):
    """B · 滚动地平线整本书写作 job：按 projection 的逐 phase OutlineRun 顺序，
    逐章「成稿 → 同步回灌记忆」，可检查点/续跑/分批。append-only（一次会话一行）。"""

    __tablename__ = "book_write"
    id = Column(Integer, primary_key=True, autoincrement=True)
    projection_id = Column(Integer)
    status = Column(String, default="writing")   # writing / paused / done / failed
    stage = Column(String, default="")           # 当前进度文案
    chapters_total = Column(Integer, default=0)
    chapters_done = Column(Integer, default=0)
    current_chapter = Column(Integer)
    log_json = Column(JSON)                       # [{chapter, status, attempts, reingest}]
    phase_reviews_json = Column(JSON)             # 阶段末跨章 holistic 复审 + 伏笔燃尽 + 体量
    error = Column(Text)
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class CraftSnippet(Base):
    """原著「笔法片段」库的一条:从某章抽出的某类笔法片段(打斗/潜台词对话/章节钩子…)。

    每类**留全部条目**(不截断);``representativeness`` 仅用于消费端排序与 few-shot
    取高分,不作删除依据。``excerpt`` 是本地私有语料的原文片段,仅作仿写参考
    (与 StyleProfile.scene_exemplars_json 同性质)。
    """

    __tablename__ = "craft_snippet"
    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String, index=True)   # combat / dialogue_subtext / hook (MVP)
    subtype = Column(String)                # combat:duel/melee/war ; hook:opening/ending
    chapter_number = Column(Integer, index=True)
    char_start = Column(Integer)
    char_end = Column(Integer)
    excerpt = Column(Text)
    representativeness = Column(Integer, default=50)  # 0-100 典型性
    tags_json = Column(JSON, default=list)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class CraftStyleCard(Base):
    """每个笔法类别一张拆解卡(聚合层):句式/节奏/修辞/信息释放/正反例等。

    ``card_json`` 可直接拼进写作 agent 的 system prompt(按场景类型选对应卡)。
    """

    __tablename__ = "craft_style_card"
    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String, unique=True, index=True)
    snippet_count = Column(Integer, default=0)
    card_json = Column(JSON)
    cost_usd = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow)
