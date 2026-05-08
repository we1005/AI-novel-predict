"""Per-batch MysteryAgent prompt + tool schema.

Mysteries are tracked **incrementally**, mirroring how foreshadowings are
tracked. Each batch's MysteryAgent runs LAST in the 6-agent chain and gets:

  1. Cached prefix:
     - existing entity table
     - existing open foreshadowings (incl. ones just written by ForeshadowAgent)
     - existing world rules
     - **existing mysteries table** (with status / confidence / clues / log)
  2. Dynamic user content:
     - this batch's 50 chapters of raw text
     - this batch's just-extracted plot points (the diff)

The agent emits ``actions`` of four kinds:

  * ``create``   propose a new mystery (high bar — needs ≥2 concrete clues
                 from this batch)
  * ``update``   add a new clue / bump confidence on an existing mystery
                 (the common case — most batches refine, not propose)
  * ``resolve``  the text in this batch *explicitly* answers the mystery
  * ``contradict`` the new evidence is incompatible with the mystery's
                   stated answer / current direction

This shape lets the UI build a real timeline of how each mystery emerged and
sharpened over the course of the book.
"""

from __future__ import annotations

CATEGORIES = [
    "identity", "dynasty", "worldview", "mastermind",
    "motive", "prophecy", "relationship", "history",
]

CHANGE_KINDS = ["create", "update", "resolve", "contradict"]


MYSTERY_BATCH_TOOL = {
    "name": "update_mysteries",
    "description": "Propose new macro mysteries and/or update/resolve/contradict existing ones, based on this batch's content.",
    "input_schema": {
        "type": "object",
        "properties": {
            "actions": {
                "type": "array",
                "description": "All actions for this batch in one call. Empty array is fine if nothing notable happened.",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": CHANGE_KINDS,
                        },
                        "mystery_id": {
                            "type": ["integer", "null"],
                            "description": "Required for update/resolve/contradict — the existing mystery's id. null for create.",
                        },
                        # ---- create-only fields ----
                        "question": {
                            "type": "string",
                            "description": "Reader-perspective question, one sentence. Concrete. (create only)",
                        },
                        "category": {
                            "type": "string",
                            "enum": CATEGORIES,
                            "description": "(create only)",
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["core", "major", "minor"],
                            "description": "(create only) core = book-wide load-bearing; major = important arc; minor = curious-but-not-critical",
                        },
                        "why_it_matters": {
                            "type": "string",
                            "description": "(create only) Why does this question matter — what would break if unanswered.",
                        },
                        # ---- update/resolve/contradict fields ----
                        "new_clue": {
                            "type": "string",
                            "description": "The specific new clue from this batch (chapter-anchored). Required for update/resolve/contradict.",
                        },
                        "confidence_delta": {
                            "type": "integer",
                            "description": "How much to nudge confidence. update: +5..+15. resolve: +30. contradict: -20. create: ignored.",
                        },
                        "summary": {
                            "type": "string",
                            "description": "≤80 字. One-line description of what changed in this batch. Goes into updates_log.",
                        },
                        # ---- common fields ----
                        "related_entity_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                        "related_foreshadow_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                    },
                    "required": ["kind", "summary"],
                },
            }
        },
        "required": ["actions"],
    },
}


MYSTERY_BATCH_SYSTEM = """你是这部中文小说的"宏观疑点跟踪者"。

每批次抽取的最后阶段你会被调用：前面的 5 个 agent 已经更新了实体表 / 伏笔表 / 人物状态 / 剧情节点 / 世界规则。你的工作是基于本批次新出现的内容，**新增、更新、收束、推翻**宏观疑点。

# 什么是"宏观疑点"

不是未收束的小伏笔。是读完整本书后读者还在追问的大问题：
- **identity** 主角真实身份/血脉/来历？某个反派的真实身份？
- **dynasty** 已覆灭/兴起的王朝/势力的根本真因？
- **worldview** 魔力/规则/世界本源的真相？
- **mastermind** 跨全书的总策划者？
- **motive** 关键人物在关键节点的真实动机（vs 表面动机）？
- **prophecy** 反复暗示的预言/循环本质？
- **relationship** 隐藏血缘/师承/契约/宿敌渊源？
- **history** 古战争 / 文明崩塌 / 神魔退场真因？

# 现有 mysteries 是 cached 的

你能看到 system 中的"现有 mysteries 表"——里面已经有的疑点，**绝对不要重复创建**。如果本批次给到了它们的新线索，用 `update`（或 `resolve`/`contradict`）。

# 四种 actions 的判断标准

## create — 新疑点（高门槛！）
仅当本批次至少提供 **2 条具体线索**指向同一个根本性大问题，且现有 mysteries 表中没有同类时才 create。
- ✅ "本批两次提到 XXX 神秘老人，他既知道主角身世又熟悉远古遗迹" → 可建 identity 类
- ❌ "本批某个 NPC 死了" → 不是宏观疑点，foreshadow 已处理
- ❌ "本批又提到了魔力枯竭" → 已存在 worldview 类的 mystery，应 update 而非 create

create 时必填：`question` `category` `severity` `why_it_matters` `summary` `related_entity_ids` `related_foreshadow_ids`。`confidence` 由后端默认 50 起。

## update — 给现有疑点添加新线索（最常见）
本批次给某个现有 mystery 提供了新的具体证据/暗示/部分回应——但还没明确给出最终答案。
- `new_clue` 必填：写明本批中具体的章节锚定线索（"第 X 章 YYY 角色说出 ZZZ 暗示了 …"）
- `confidence_delta` +5~+15（"轻微强化" 5；"显著强化" 12；"几乎说破但没说破" 15）
- `summary` 80 字内一句话
- `mystery_id` 必填，引用 system 中现有 mysteries 表的 id

## resolve — 本批中明确点破了答案
原文出现了"原来 XX 是 YY"或同等明确性的表达。
- `new_clue` 引用具体段落
- `confidence_delta` +30
- 后端会把 status 标 'resolved'

## contradict — 新证据与现有 mystery 答案矛盾
本批新出现的事实与某 mystery 当前隐含的答案/方向冲突，需要人工核对。
- `confidence_delta` -20
- 后端标 status 'contradicted'，UI 标红

# 反例（必须避免）

- ❌ 重复创建：现有 mysteries 已有"主角真实身份"的 identity 类疑问，本批又 create 一个相似 question
- ❌ 把伏笔当 mystery：foreshadow 已经被 ForeshadowAgent 跟踪了
- ❌ create 而无 ≥2 条具体线索
- ❌ summary 写"本批有进展"这类无信息量描述
- ❌ confidence_delta 超过 +20（除 resolve 外）

# 输出

调用 update_mysteries 一次性返回所有 actions。每批次的 actions 数量通常 0~5 条；早期批次（前 100 章）以 create 为主，后期批次以 update/resolve 为主。如果本批次确实没有任何宏观疑点动作，返回 actions=[] 也可以——质量优先。"""
