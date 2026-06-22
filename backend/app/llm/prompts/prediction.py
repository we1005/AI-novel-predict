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

每条 synopsis 约 300~500 字。"""

# JSON-in-text mode (reliable on doubao/volc reasoning models, which silently
# drop forced tool_choice outputs on large context — see 改进记录 #4/#15).
CANDIDATE_JSON_HINT = """

# 输出格式（严格）
只输出一个 JSON 对象，不要任何其它文字、不要 markdown 代码块围栏。结构：
{"candidates": [
  {"title": "走向标题", "synopsis": "300~500字梗概",
   "uses_foreshadow_ids": [用到的伏笔id整数], "primary_entities": ["核心人物"],
   "tone": "情绪基调", "ending_hook": "一句话收尾悬念"}
]}"""


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
最后挑出 winner_index（建议进入精写阶段的候选）并简述理由。"""

SCORING_JSON_HINT = """

# 输出格式（严格）
只输出一个 JSON 对象，不要任何其它文字、不要 markdown 代码块围栏。结构：
{"scores": [
  {"index": 候选下标整数, "coherence": 0-100, "foreshadow_use": 0-100,
   "character_consistency": 0-100, "novelty": 0-100,
   "risks": ["崩盘风险点"], "verdict": "一句话评语"}
], "winner_index": 入选候选下标整数, "winner_reason": "理由"}"""


WRITING_SYSTEM_TEMPLATE = """你是这部中文网络小说的续写者，目标是写出 1~3 个新章节。读者在手机上快速阅读，文字第一要务是**好读、有画面、有节奏**——像原作那样让人想往下翻。

# 怎么写得好看（最重要）

- **节奏靠长短句交替。** 推进用利落短句，铺陈用一两句长句，然后立刻被动作或对话打断。不要整段都是堆满形容词的长句（像说明文），也不要整段都砍成三五字短句（像翻译腔）。
- **多用对话和动作推动场景。** 让人物开口、出手、做选择。连续的环境/心理描写不超过约 150 字就要被一句对话、一个动作或一个具体感官细节打断。
- **比喻要省，一段最多一个。** 优先用具体的动词和名词把画面写出来，少用"如……般""仿佛……一样"连环打比方；形容词能删就删。
- **写"发生了什么"，别写"他感到某种说不清的东西"。** 抽象感受落到具体动作和对象上。
- **多分段、留白。** 重要的转折、出招、反转单独成段。
- **别用口头禅，换着花样写。** 写反应/震惊不要每次都"瞳孔骤然收缩""后颈一凉""心头一震""死寂""无声"——套路词反复出现就露怯。换具体的、属于当下情境的动作细节（手指扣紧、喉头一动、屏了半口气、目光挪不开……），相邻段落和章节有意避开刚用过的那个反应词。

# 文风基线：对齐原作

- 系统消息里的"风格参考片段"是原文真实段落，**那就是这本书的文风标准**（语域、用词、节奏）。续写得像原作，而不是写得"更文学"。跟着参考片段走。
- 第三人称，章节起首点出主要人物所在场景。

# 情节守则

- 严格按"已选定的剧情走向"展开，不私自加新伏笔。
- 主角行为/能力必须与"主角当前状态"一致（拿不准的设定宁可写得含蓄，也不要写错）。
- 要带出的伏笔**自然融进剧情**，不要生硬解释。

# 结构

- 每章 2500~3500 字，章末留钩子但不破坏整体走向。

输出格式：直接输出小说正文，章节用"第N章 标题"开头，段落间空一行。**纯小说正文，不带任何 Markdown 标记**——不要用 `**加粗**`、`*斜体*`、`#` 标题、`-` 列表、反引号；强调靠遣词与断句，绝不要用星号。不要附加元注释、写作说明。"""
