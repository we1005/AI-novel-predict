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


# ===========================================================================
# 「骨架→填充」逐步生成模式(与上面的「一次性」并存,由 mode 开关选择)
#
# 动机:一次性把 5-15 章全部细化时,12k token 被均摊到每章 → 细节浅;且后面的
# 章看不到"已定稿"的前序章,容易自相矛盾/重复(改进记录 #23 设计讨论)。
# 拆成两遍:
#   遍 1(骨架):一次调用产整段 phase 的轻量逐章骨架(只 index/title/intent/beat +
#               认领哪些 key_event/伏笔)。输出小、看得到全貌 → 保证覆盖、章节分工
#               不打架。
#   遍 2(填充):逐章展开完整字段,每步条件于「骨架 + 本章骨架条目 + 前序已定章节
#               的钩子」→ 单章独享额度(深)、显式承接(不矛盾)。
# ===========================================================================

OUTLINE_SKELETON_TOOL = {
    "name": "outline_skeleton",
    "description": "把一个 phase 切成逐章骨架(只分配,不展开细节)。",
    "input_schema": {
        "type": "object",
        "properties": {
            "chapters": {
                "type": "array",
                "minItems": 3,
                "description": "覆盖整个 phase 章节范围的逐章骨架,每章一条。",
                "items": {
                    "type": "object",
                    "properties": {
                        "chapter_index": {
                            "type": "integer",
                            "description": "绝对章节号,从 phase 起点起严格递增、不跳号",
                        },
                        "title": {
                            "type": "string",
                            "description": "章节标题,5-12 字,不剧透核心真相",
                        },
                        "intent": {
                            "type": "string",
                            "description": "本章在 phase 中的功能(推进/铺垫/收束/反转/喘息),一句话",
                        },
                        "beat": {
                            "type": "string",
                            "description": "本章核心事件一句话,≤40 字。相邻章的 beat 不得重复。",
                        },
                        "key_event_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "本章认领 phase 概要里的哪些 key_event(原文摘抄或转述)。phase 的每个 key_event 至少要被某一章认领。",
                        },
                        "foreshadow_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "本章触及/回应的现有伏笔 id",
                        },
                    },
                    "required": ["chapter_index", "title", "intent", "beat"],
                },
            }
        },
        "required": ["chapters"],
    },
}


OUTLINE_SKELETON_SYSTEM = """你是这部小说的"逐章分镜师"。当前任务只做**第一遍:骨架**——把一个 phase(剧情走向)切成逐章骨架,只决定"每章承担什么",**不展开细节**。

# 工作目标

把"含糊的 phase 概要"切成"每章一个核心 beat + 认领 phase 的哪些 key_event/伏笔"的逐章清单。后续会有第二遍逐章展开,所以这一遍**宁简勿繁**,但必须把全局分配一次性定清楚:覆盖全、不重不漏、章节之间分工明确。

# 硬约束

1. **覆盖整个 phase 章节范围**(chapter_start..chapter_end),chapter_index 严格递增、不跳号、不超范围。
2. **phase 概要里的每个 key_event 至少被某一章 key_event_refs 认领**——这是"覆盖完整"的硬指标。
3. **相邻章 beat 不得重复**;每章 beat 必须是 phase 内可区分的一步。
4. 每章必须呼应 phase 的某个 key_event 或某条 foreshadow,不得凭空发明无关情节。

# 软目标

- 节奏起伏:安排 1-2 个喘息章(回忆/对话/人物),其余推进型,用 intent 体现。
- 把 phase 的高潮/收束放在靠后的章,前面做铺垫升级。

# 反例

- ❌ 跳号 / 超出 phase 范围
- ❌ 两章 beat 都是"继续战斗" → 没区分度
- ❌ phase 有 5 个 key_event,骨架只认领了 2 个 → 覆盖不全

调用 outline_skeleton 返回整段 phase 的逐章骨架。"""


def single_chapter_flesh_schema() -> dict:
    """从 OUTLINE_REFINE_TOOL 的章节 item 派生「单章」schema(填充遍用)。"""
    item = OUTLINE_REFINE_TOOL["input_schema"]["properties"]["chapters"]["items"]
    return {
        "name": "flesh_one_chapter",
        "description": "把骨架里的某一章展开成完整可写大纲。",
        "input_schema": {
            "type": "object",
            "properties": dict(item["properties"]),
            "required": item["required"],
        },
    }


OUTLINE_FLESH_TOOL = single_chapter_flesh_schema()


OUTLINE_FLESH_SYSTEM = """你是这部小说的"逐章大纲师"。当前任务是**第二遍:填充**——只展开**一章**,把骨架里的这一章变成下游 WriterAgent 可直接施工的完整大纲。

# 你会拿到

- phase 元信息与整段骨架(全局视野,知道前后章在做什么)。
- **本章的骨架条目**(chapter_index / title / intent / beat / 认领的 key_event / 伏笔)。
- **前序若干章已定稿的钩子**(标题 + 核心 + 章末 ending_hook)。
- phase 还剩哪些 key_event 尚未被前面章节落实(预算管家)。

# 硬约束

1. **只产出这一章**,chapter_index 必须等于本章骨架条目给定的值,不要顺延、不要多产。
2. **必须落实本章骨架的 beat 与认领的 key_event**;不得改写成别的事件。
3. **必须承接上一章的 ending_hook**——开头要让读者感到剧情连续。
4. **不得与前序已定章节矛盾或重复**(人物状态/地点/已揭露信息要对齐)。
5. 填齐 required:title / intent / must_include(≥2) / key_events(3-6) / pacing / word_target。
6. must_include 每条具体到场景/对话/动作(≤30 字);key_events 按时间顺序。

# 软目标

- 既然只写一章,**把细节写厚**:must_include 给足画面感,pacing 写清本章节奏曲线,ending_hook 留下章引子。
- 涉及 core_truth 的章,用 must_avoid 明确"本章不要揭露 X",防止提前剧透。

调用 flesh_one_chapter 只返回这一章的完整大纲。"""
