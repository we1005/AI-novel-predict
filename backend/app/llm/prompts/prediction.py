"""Prompts for the three-stage prediction pipeline.

Stage A — diverge (high temperature, propose N candidates).
Stage B — constrain (low temperature, score and rank candidates).
Stage C — write (medium temperature, expand the chosen candidate into prose).
"""

from __future__ import annotations

CANDIDATE_TOOL = {
    "name": "propose_candidates",
    "description": "Propose N divergent plot directions for the next ~3 chapters.",
    "input_schema": {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "synopsis": {"type": "string"},
                        "uses_foreshadow_ids": {"type": "array", "items": {"type": "integer"}},
                        "primary_entities": {"type": "array", "items": {"type": "string"}},
                        "tone": {"type": "string"},
                        "ending_hook": {"type": "string"},
                    },
                    "required": ["title", "synopsis", "uses_foreshadow_ids"],
                },
            }
        },
        "required": ["candidates"],
    },
}

CANDIDATE_SYSTEM = """你是这部中文小说的续写策划。基于已确立的伏笔/人物状态/世界观，提出 N 条**有创造力且自洽**的剧情走向候选。

硬约束：
- 必须使用至少 2 条"现有未收束伏笔表"中的伏笔（在 uses_foreshadow_ids 中给出 id）。
- 不得违反"现有世界规则表"。
- 不得改变主角已有的境界/物品/关系，除非走向中明确写出"如何改变"。

软目标（追求差异化）：
- N 条候选风格/方向不应趋同；尝试不同情绪基调（紧张/温情/悬疑/史诗）。
- ending_hook 用一句话给出本走向收尾的悬念，让读者想看下一段。

每条 synopsis 约 300~500 字。调用 propose_candidates。"""


SCORING_TOOL = {
    "name": "score_candidates",
    "description": "Score each candidate on coherence, foreshadow utilization, character consistency, novelty.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "coherence": {"type": "integer", "minimum": 0, "maximum": 100},
                        "foreshadow_use": {"type": "integer", "minimum": 0, "maximum": 100},
                        "character_consistency": {"type": "integer", "minimum": 0, "maximum": 100},
                        "novelty": {"type": "integer", "minimum": 0, "maximum": 100},
                        "risks": {"type": "array", "items": {"type": "string"}},
                        "verdict": {"type": "string"},
                    },
                    "required": [
                        "index",
                        "coherence",
                        "foreshadow_use",
                        "character_consistency",
                        "novelty",
                        "verdict",
                    ],
                },
            },
            "winner_index": {"type": "integer"},
            "winner_reason": {"type": "string"},
        },
        "required": ["scores", "winner_index", "winner_reason"],
    },
}

SCORING_SYSTEM = """你是这部小说的续写约束校验员。基于完整伏笔表、人物状态、世界规则，对每条候选打 4 个维度的分（0-100）：

- coherence 自洽性：是否违反已有设定？
- foreshadow_use 伏笔利用：是否真正用到候选自称"用到"的伏笔？是否有"借伏笔"嫌疑？
- character_consistency 人物一致性：人物动机/能力/性格是否符合既往设定？
- novelty 新鲜度：是否在主线上有足够推进？避免炒冷饭。

risks 是该走向最可能崩盘的 2~3 个点。
最后挑出 winner_index（建议进入精写阶段的候选）并简述理由。

调用 score_candidates。"""


WRITING_SYSTEM_TEMPLATE = """你是这部中文小说的续写者，目标是写出 1~3 个新章节。

**风格守则**：
- 严格继承原作文风（语速、句式、画面感）。系统消息中提供了"风格参考片段"——是从原文检索到的相关段落，写作时参考其用词与节奏。
- 第三人称，章节起首点出主要人物所在场景。

**情节守则**：
- 严格按照"已选定的剧情走向"展开，不要私自加新的伏笔。
- 主角行为/能力必须与提供的"主角当前状态"一致。
- 用到的伏笔必须自然带出，不要生硬解释。

**结构**：
- 每章 2500~3500 字。
- 每章末留有钩子，但不破坏整体走向。

输出格式：
直接输出小说正文，章节用"第N章 标题"开头。不要附加元注释。"""
