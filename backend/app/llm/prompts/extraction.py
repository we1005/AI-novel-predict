"""Prompts and tool schemas for the five extraction agents.

Design rules
------------
* Stable ordering — entity tables and foreshadow tables go through
  ``stable_json`` so prompt-cache prefixes stay byte-identical between calls.
* Tool use over JSON-by-pleading — every agent declares a ``tools`` schema and
  ``tool_choice`` forces the model to fill it.
* Few-shot enums for fuzzy concepts (foreshadow types) so the model stops
  inventing new categories.
"""

from __future__ import annotations

from typing import Any

ENTITY_TYPES = ["person", "faction", "item", "location", "skill", "concept"]
FORESHADOW_TYPES = ["person", "item", "faction", "mystery", "promise", "prophecy"]


# ---------------------------------------------------------------------------
# Entity agent
# ---------------------------------------------------------------------------

ENTITY_TOOL = {
    "name": "record_entities",
    "description": "Record any new named entities introduced in the chapters provided.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ENTITY_TYPES},
                        "name": {"type": "string"},
                        "aliases": {"type": "array", "items": {"type": "string"}},
                        "first_appear_chapter": {"type": "integer"},
                        "description": {"type": "string"},
                        "match_existing_id": {
                            "type": ["integer", "null"],
                            "description": "If this entity refers to an EXISTING entity (by alias / nickname), set its id; otherwise null.",
                        },
                    },
                    "required": ["type", "name", "first_appear_chapter", "description"],
                },
            }
        },
        "required": ["entities"],
    },
}

ENTITY_SYSTEM = """你是中文小说的实体抽取助手。任务：阅读给定章节，抽出新登场的命名实体。

类型枚举：
- person  人物（含主角、配角、有名字的反派）
- faction 势力/组织/学派/公会/帝国
- item    物品/法宝/秘籍/道具
- location 地点/城市/秘境/世界
- skill   功法/技能/招式/法术
- concept 概念/术语/世界规则相关名词（仅当作为重要概念被引入时）

要求：
1. 仅记录明确出现"人物名/势力名/物品名"等具名实体；模糊指代（"那个老头"）不算。
2. 如果你判断该实体其实是"已知实体"的别名/绰号/字号，将 match_existing_id 设为对应的 id（已知实体表见 system 中的"现有实体表"），name 仍写本批中出现的称呼。
3. description 用 1~2 句中文概括，不抄长段原文。
4. first_appear_chapter 必须是这批章节范围内的具体章节号。
5. 调用 record_entities 工具一次性返回结果。"""


# ---------------------------------------------------------------------------
# Foreshadow agent
# ---------------------------------------------------------------------------

FORESHADOW_TOOL = {
    "name": "record_foreshadowings",
    "description": "Record newly planted foreshadowings AND any open foreshadowings resolved in this batch.",
    "input_schema": {
        "type": "object",
        "properties": {
            "planted": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "planted_chapter": {"type": "integer"},
                        "type": {"type": "string", "enum": FORESHADOW_TYPES},
                        "description": {"type": "string"},
                        "planted_excerpt": {"type": "string"},
                        "related_entity_names": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["planted_chapter", "type", "description"],
                },
            },
            "resolved": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "foreshadow_id": {"type": "integer"},
                        "resolved_chapter": {"type": "integer"},
                        "resolved_description": {"type": "string"},
                    },
                    "required": ["foreshadow_id", "resolved_chapter", "resolved_description"],
                },
            },
        },
        "required": ["planted", "resolved"],
    },
}

FORESHADOW_SYSTEM = """你是中文小说的伏笔跟踪助手。

什么是伏笔（要识别的）：
- 谜团：一个尚未揭示答案的疑问（来历、身份、宝物归属…）
- 承诺：人物间的承诺/誓言/约定
- 预言：被明示或暗示的预言/卦象
- 道具：被特意描写但当下未发挥作用的物品
- 人物：被提及但未登场/未深入的人
- 势力：被提及但未正面展开的势力

什么不是伏笔：
- 当章已闭合的小冲突（比如打架打赢了）
- 纯背景描写（天气、街景）
- 已经收束的事项（除非是新的开放问题）

收束判定：
- "现有未收束伏笔表"在 system 中给出。本批中如果某条被回应/给出答案/事件发生，写到 resolved。
- 部分回应也算收束（写明 how 即可）。

调用 record_foreshadowings，planted 和 resolved 两个数组都必须给出（可为空数组）。"""


# ---------------------------------------------------------------------------
# State agent
# ---------------------------------------------------------------------------

STATE_TOOL = {
    "name": "record_state_changes",
    "description": "Record state diffs for tracked key entities across this batch of chapters.",
    "input_schema": {
        "type": "object",
        "properties": {
            "states": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "entity_name": {"type": "string"},
                        "chapter": {"type": "integer"},
                        "change": {
                            "type": "object",
                            "properties": {
                                "realm": {"type": "string"},
                                "items_gained": {"type": "array", "items": {"type": "string"}},
                                "items_lost": {"type": "array", "items": {"type": "string"}},
                                "skills_gained": {"type": "array", "items": {"type": "string"}},
                                "relationships_changed": {"type": "array", "items": {"type": "string"}},
                                "alive": {"type": "boolean"},
                                "note": {"type": "string"},
                            },
                        },
                    },
                    "required": ["entity_name", "chapter", "change"],
                },
            }
        },
        "required": ["states"],
    },
}

STATE_SYSTEM = """你跟踪小说中关键人物的状态演变。

只记录"重要人物列表"中的实体（system 中给出，主要是主角和核心配角）。
对每个重要 diff 输出一条记录：
- realm: 境界/等级（如有变化）
- items_gained / items_lost: 获得/失去的关键物品
- skills_gained: 学到的功法/技能
- relationships_changed: "拜某人为师" / "与某人结仇" / "结拜" 等
- alive: 仅在生死状态发生变化时设
- note: 一句话概括本次变化的背景

只调用 record_state_changes 一次。"""


# ---------------------------------------------------------------------------
# Plot agent
# ---------------------------------------------------------------------------

PLOT_TOOL = {
    "name": "record_plot_points",
    "description": "Record key plot points (turning points, major battles, revelations).",
    "input_schema": {
        "type": "object",
        "properties": {
            "plot_points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "chapter": {"type": "integer"},
                        "summary": {"type": "string"},
                        "importance": {"type": "integer", "minimum": 0, "maximum": 100},
                        "involved_entity_names": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["chapter", "summary", "importance"],
                },
            }
        },
        "required": ["plot_points"],
    },
}

PLOT_SYSTEM = """你是小说剧情节点提取助手。识别本批中"对全书走向有影响的关键节点"。

只挑真正重要的（importance ≥ 40）：
- 主角境界突破/重大蜕变
- 主要势力间冲突的爆发或收尾
- 重大秘密被揭开
- 重要 NPC 死亡/登场
- 主线方向发生改变的关键决策

importance 评分参考：
- 80~100 全书关键转折
- 60~79 主线推进
- 40~59 重要支线节点

每批最多挑 10~20 个，宁缺毋滥。调用 record_plot_points。"""


# ---------------------------------------------------------------------------
# World rules agent
# ---------------------------------------------------------------------------

WORLD_TOOL = {
    "name": "record_world_rules",
    "description": "Record newly introduced world-building terms / setting rules.",
    "input_schema": {
        "type": "object",
        "properties": {
            "rules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "term": {"type": "string"},
                        "definition": {"type": "string"},
                        "first_chapter": {"type": "integer"},
                    },
                    "required": ["term", "definition", "first_chapter"],
                },
            }
        },
        "required": ["rules"],
    },
}

WORLD_SYSTEM = """你抽取小说的"世界设定/规则术语"——书内自洽性的来源。

只在以下情况记录：
- 引入新的境界体系/等级名（如"魔法师 -> 大魔法师 -> 大魔导师"）
- 引入新的世界观规则（如"魔力衰竭""时间倒流的限制"）
- 引入新的种族/血脉/传承
- 引入需要持续维护的术语

不要记录单次出现的物品/人物（那是 EntityAgent 的活）。

只调用 record_world_rules。"""


def all_agents() -> dict[str, dict[str, Any]]:
    from .mystery_per_batch import MYSTERY_BATCH_SYSTEM, MYSTERY_BATCH_TOOL

    return {
        "entity": {"system": ENTITY_SYSTEM, "tool": ENTITY_TOOL},
        "foreshadow": {"system": FORESHADOW_SYSTEM, "tool": FORESHADOW_TOOL},
        "state": {"system": STATE_SYSTEM, "tool": STATE_TOOL},
        "plot": {"system": PLOT_SYSTEM, "tool": PLOT_TOOL},
        "world": {"system": WORLD_SYSTEM, "tool": WORLD_TOOL},
        "mystery": {"system": MYSTERY_BATCH_SYSTEM, "tool": MYSTERY_BATCH_TOOL},
    }
