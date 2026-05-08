"""Single-shot LLM pass to label character roles and pairwise relationships.

Inputs (cached):
  * Top-N person entities with first_appear_chapter, importance, description
  * Raw "relationships_changed" lines collected from entity_states.diff_json
  * High-importance plot points (importance ≥ 60) summaries
  * Open foreshadowings text (some hide relationship reveals)

Output: a list of role assignments per person + a list of directed relationships
between people, with concise labels suitable for edge captions.
"""

from __future__ import annotations

ROLES = ["protagonist", "antagonist", "ally", "supporting", "minor"]


RELATIONSHIPS_TOOL = {
    "name": "label_roles_and_relationships",
    "description": "Assign narrative roles to top characters and extract pairwise directed relationships between them.",
    "input_schema": {
        "type": "object",
        "properties": {
            "roles": {
                "type": "array",
                "description": "对每个 input 中的人物给一个角色判定。可以漏（漏的会被默认 minor）。",
                "items": {
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "integer"},
                        "role": {"type": "string", "enum": ROLES},
                        "rationale": {"type": "string", "description": "≤40 字判定理由"},
                    },
                    "required": ["entity_id", "role"],
                },
            },
            "relationships": {
                "type": "array",
                "description": "成对的有向关系。同一 (from→to) 可以多种标签，写成多条记录。",
                "items": {
                    "type": "object",
                    "properties": {
                        "from_entity_id": {"type": "integer"},
                        "to_entity_id": {"type": "integer"},
                        "label": {
                            "type": "string",
                            "description": "短标签，2-12 字。例：『师徒』『宿敌/眼中钉』『同路人与潜在恋人』",
                        },
                        "description": {
                            "type": "string",
                            "description": "≤80 字关系描述：在哪几章如何形成、当前状态",
                        },
                        "first_chapter": {"type": "integer"},
                        "status": {"type": "string", "enum": ["active", "ended"]},
                        "weight": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "description": "叙事权重 1-10：在主线中的存在感",
                        },
                    },
                    "required": ["from_entity_id", "to_entity_id", "label"],
                },
            },
        },
        "required": ["roles", "relationships"],
    },
}


RELATIONSHIPS_SYSTEM = """你是这部中文小说的人物关系分析员。基于已结构化的全书数据（人物表、状态变更行、剧情节点、未收束伏笔），完成两件事：

# 任务 1：角色分类（roles）

为输入中的每个人物分配一个角色：
- **protagonist**：主角。通常 first_appear_chapter=1 且 importance 极高。**整部书最多 1 个**。
- **antagonist**：核心反派/对立面。能与主角形成主线冲突。可以 0-3 个。
- **ally**：主角的核心盟友/师/友/伴侣。深度参与主线。
- **supporting**：重要配角。有戏份但不是主线核心驱动者。
- **minor**：龙套，仅出场少量章节。

# 任务 2：关系抽取（relationships）

抽出**人物两两之间的有向关系**。
- 优先抽 protagonist 与其他人的关系（最重要）。
- 然后抽 antagonist 与其他人、ally 之间的关系。
- minor 之间的关系一般不抽，除非该关系本身是核心剧情。

每条关系要求：
- **label**：2-12 字的精炼短语。可以是单一类型（"师徒"）也可以是组合（"宿敌/眼中钉"、"同路人与潜在恋人"）。**避免空话**如"朋友"、"认识"——要写出叙事张力。
- **description**：≤80 字。说明该关系如何形成、目前状态、为什么重要。
- **first_chapter**：关系初次成立的章节号（推断即可）。
- **status**：active（仍在持续）或 ended（已结束/转化/一方死亡）。
- **weight** 1-10：在主线中的叙事权重。主角与核心反派的对立 9-10；主角与重要伴侣 8-9；主角与重要配角 5-7；其他配角间 2-4。

# 关键判定标准

- **方向性**：如果 A 是 B 的师傅，则记录 from=A, to=B label="师徒（A 为 B 师）"，或者拆成两条 A→B "师傅" + B→A "弟子"。任选其一保持一致即可。
- **多重标签合并**：如 A 与 B 既是技术搭档又是潜在恋人，写一条 label="技术搭档与情感羁绊"。
- **去重**：同一 (from, to, label) 不要重复。

# 反例（避免）

- ❌ label="朋友" → 太弱，必须更具体
- ❌ description="他们是朋友" → 没信息量
- ❌ 关系只出现 1 次的二线 NPC 之间互连 → 噪音

调用 label_roles_and_relationships。"""
