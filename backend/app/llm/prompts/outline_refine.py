"""Prompt for refining an arc/predict winner into a chapter-by-chapter outline
covering one phase at a time.

Why per-phase instead of all-at-once:
  - Quality: outline for chapter N+30 should be informed by what was actually
    written in chapter N+5..N+15 (not guessed at generation time).
  - Cost: a 5-15 chapter chunk fits comfortably; 80-chapter chunk explodes
    the response and tends to repeat.
  - User control: the user can write/review one phase, then refine the next.
"""

from __future__ import annotations

OUTLINE_REFINE_TOOL = {
    "name": "refine_phase_outline",
    "description": "Expand one phase of an arc (or a predict candidate's range) into a chapter-by-chapter outline.",
    "input_schema": {
        "type": "object",
        "properties": {
            "chapters": {
                "type": "array",
                "minItems": 3,
                "description": "至少 3 章。每章一个明确的可写大纲（不是含糊概要）。",
                "items": {
                    "type": "object",
                    "properties": {
                        "chapter_index": {
                            "type": "integer",
                            "description": "绝对章节号，从 phase 起点开始递增",
                        },
                        "title": {
                            "type": "string",
                            "description": "章节标题，5-12 字，避免剧透核心真相",
                        },
                        "intent": {
                            "type": "string",
                            "description": "本章在 phase 中的功能（推进/铺垫/收束/反转/喘息）一句话",
                        },
                        "must_include": {
                            "type": "array",
                            "minItems": 2,
                            "items": {"type": "string"},
                            "description": "至少 2 条本章必须出现的具体元素（场景/对话/动作）。每条≤30 字。",
                        },
                        "must_avoid": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "本章绝对不能写的内容（避免剧透 / 提前抖包袱 / 角色 OOC 行为）",
                        },
                        "key_events": {
                            "type": "array",
                            "minItems": 3,
                            "maxItems": 6,
                            "items": {"type": "string"},
                            "description": "3-6 个本章的关键事件，按时间顺序，每个≤30 字",
                        },
                        "foreshadow_ids_addressed": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "本章触及/回应/收束的现有伏笔 id",
                        },
                        "foreshadow_ids_planted": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "本章新埋的伏笔——通常空数组（成稿后由 ForeshadowAgent 二次抽取）",
                        },
                        "involved_entities": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "本章登场/活跃的关键实体名（人物/势力/物品）",
                        },
                        "pacing": {
                            "type": "string",
                            "description": "节奏说明：『首段慢热-中段紧张-结尾留悬念』之类。≤40 字。",
                        },
                        "word_target": {
                            "type": "integer",
                            "description": "目标字数。一般 2500-3500。",
                        },
                        "ending_hook": {
                            "type": "string",
                            "description": "章末钩子——一句话埋下下章引子",
                        },
                    },
                    "required": [
                        "chapter_index", "title", "intent",
                        "must_include", "key_events",
                        "pacing", "word_target",
                    ],
                },
            }
        },
        "required": ["chapters"],
    },
}


OUTLINE_REFINE_SYSTEM = """你是这部小说的"逐章大纲师"。基于已选定的剧情走向（arc winner 或 predict candidate）和当前 phase 信息，把它细化成**逐章可写**的大纲。

# 工作目标

把"含糊的剧情走向（200-500 字）"变成"具体的章节施工图"——下游 WriterAgent 看到大纲就知道该章 3000 字怎么排：哪个开头、写到哪、哪个画面、什么对话、章末怎么钩。

# 硬约束

1. **章节数量**：覆盖给定 phase 的整个章节范围（chapter_start..chapter_end）。一般 5-15 章，平均每章对应 phase 概要中 1-2 个 key event。
2. **必须填齐 required 字段**：title / intent / must_include / key_events / pacing / word_target。
3. **chapter_index 必须严格递增**且全部落在 phase 给定范围内。
4. **must_include ≥ 2 条**：少于 2 条意味着本章过空，应该和邻章合并。
5. **key_events 3-6 条**：少于 3 章节太薄；多于 6 章节太满会塞不下 3000 字。
6. **每章必须呼应 phase 的某个 key_event 或某条 foreshadow**——大纲不能凭空发明无关情节。

# 软目标

- **节奏分布**：每个 phase 应有 1-2 个"喘息章"（人物刻画、回忆、对话），其余推进型；pacing 字段要分别体现。
- **must_avoid 鼓励填**：尤其是涉及 core_truth 的章节，明确写"本章不要揭露 X"，避免 Writer 提前剧透。
- **involved_entities 显式列出**：让 ConsistencyReviewer 后续好对照人物档案。
- **章节标题**：让人想读下去，不要透关键真相。

# 反例

- ❌ "林云继续修炼" → intent 太空泛
- ❌ must_include = ["推进剧情"] → 抽象
- ❌ key_events = ["发生了大事"] → 没说什么事
- ❌ chapter_index 跳号 / 超出 phase 范围
- ❌ 所有章节 pacing 都是"紧张"——节奏没有起伏

调用 refine_phase_outline 一次性返回所有章节大纲。"""
