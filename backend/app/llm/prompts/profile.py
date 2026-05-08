"""ProfileBuilder prompt + tool schema.

Per-character LLM call that distills already-extracted structured data
(entity description, state diffs, relationships, foreshadowings involving
the character) into an actor-ready profile that the simulator and
interview agent can use.
"""

from __future__ import annotations

PROFILE_TOOL = {
    "name": "build_character_profile",
    "description": "Synthesize a structured actor profile for one character.",
    "input_schema": {
        "type": "object",
        "properties": {
            "bio": {
                "type": "string",
                "description": "1-2 段、≤300 字。综合身世/外貌/出身/当前身份/重要标签",
            },
            "desires": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string"},
                "description": "3-5 条核心欲望/目标。每条 ≤30 字。具体不空泛",
            },
            "fears": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string"},
                "description": "2-4 条核心恐惧/底线",
            },
            "moral_compass": {
                "type": "string",
                "description": "≤120 字。道德取向：什么事会做、什么事绝不做、灰色地带",
            },
            "voice_style": {
                "type": "string",
                "description": "≤120 字。说话风格：语气 / 用词 / 口头禅 / 是否含糊其辞",
            },
            "typical_actions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-5 条该角色面对压力/惊讶/愤怒等情境的典型反应",
            },
            "relationships_summary": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "label": {"type": "string", "description": "如『师徒』『宿敌』『同盟』"},
                        "attitude": {
                            "type": "string",
                            "description": "≤40 字。该角色对对方的态度（信任/利用/敌视/愧疚 等具体描述）",
                        },
                    },
                    "required": ["name", "label", "attitude"],
                },
                "description": "对方为本角色已知的核心关系。3-8 条",
            },
            "secrets_known": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "secret": {"type": "string"},
                        "learned_chapter": {"type": "integer"},
                    },
                    "required": ["secret"],
                },
                "description": "本角色已经知道的关键秘密（已收束伏笔 + 状态变化中显式获得的信息）",
            },
            "secrets_hidden": {
                "type": "array",
                "items": {"type": "string"},
                "description": "本角色自己藏着、未对外公开的秘密",
            },
            "arc_so_far": {
                "type": "string",
                "description": "≤300 字。该角色截至当前章节的成长轨迹概括：从哪到哪，关键转折",
            },
        },
        "required": ["bio", "desires", "fears", "voice_style", "arc_so_far"],
    },
}


PROFILE_SYSTEM = """你为这部中文小说的某一个角色构建"actor profile"——一份能让该角色在剧情仿真中独立做决策的档案。

# 输入

system 中提供了：
- 该角色的实体记录（first_appear_chapter / description / importance）
- 该角色全部 entity_states（按章节排序的状态变更）
- 该角色相关的 relationships（其它已结构化的关系）
- 涉及该角色的 foreshadowings（已收束 + 未收束）
- 涉及该角色的 plot_points（高 importance）

# 输出守则

- **基于已知信息**：所有字段都要从输入数据推断，不要发明新设定。
- **第三人称客观语气**写 bio / arc_so_far；voice_style / moral_compass 等"性格画像"字段则用观察者口吻。
- **desires / fears 要具体**：禁止"渴望强大"这种空话。要写"夺取死亡之书的全部章节"、"被发现是穿越者"这种具体目标。
- **secrets_known**：只列"该角色明确学到/获得"的关键秘密。不是世界规则的常识。
- **secrets_hidden**：通常包含主角的"穿越者"身份、私下计划等不对外公开的事。配角可能为空数组。
- **relationships_summary**：限制 3-8 条最重要的，附上具体态度而非笼统标签。

# 反例

- ❌ "渴望变强" → 太空泛
- ❌ moral_compass = "正派" → 没信息量
- ❌ voice_style = "话很多" → 缺乏特征

调用 build_character_profile 一次返回全部字段。"""
