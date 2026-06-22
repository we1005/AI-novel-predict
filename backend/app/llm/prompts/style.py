"""Author writing-style analysis prompt + tool schema.

Opt-in (token-heavy): samples chapters across the book and produces a structured
style profile that downstream continuation can imitate. Covers prose voice,
per-scene-type description styles, tropes, signature vocabulary, structural
habits, setting/register, and a synthesized, executable 续写指导.
"""

from __future__ import annotations

STYLE_TOOL = {
    "name": "report_style_profile",
    "description": "Structured analysis of the author's writing style, for faithful imitation in continuation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "overall_voice": {"type": "string", "description": "整体文风定性（2-4 句）：这位作者读起来是什么感觉"},
            "narrative_pov": {"type": "string", "description": "叙事视角与叙述距离（第几人称、全知/限制、叙述者态度、与人物的心理距离）"},
            "sentence_rhythm": {"type": "string", "description": "句式与节奏：长短句习惯、标点习惯、段落长度、留白与密度"},
            "register": {"type": "string", "description": "语域：用词层次（雅/俗/文白）、是否书面、是否带翻译腔/欧化句式"},
            "scene_styles": {
                "type": "object",
                "description": "分场景类型的写法特点（每条 1-3 句，要具体、可模仿）",
                "properties": {
                    "combat": {"type": "string", "description": "打斗/动作场景写法"},
                    "scenery": {"type": "string", "description": "景物/环境/氛围描写写法"},
                    "character": {"type": "string", "description": "人物外貌/神态/动作刻画写法"},
                    "dialogue": {"type": "string", "description": "对话风格：语气、长短、潜台词、标签习惯"},
                    "psychology": {"type": "string", "description": "心理活动/内心独白写法"},
                    "plot_advancement": {"type": "string", "description": "推进剧情的手法：节奏、转场、信息释放、悬念铺设"},
                },
                "required": ["combat", "scenery", "character", "dialogue", "psychology", "plot_advancement"],
            },
            "tropes": {"type": "array", "items": {"type": "string"}, "description": "作者常用的套路/桥段/结构母题（5-10 条）"},
            "signature_vocabulary": {"type": "array", "items": {"type": "string"}, "description": "高频或标志性的词汇、意象、惯用表达（8-15 条）"},
            "structural_habits": {"type": "string", "description": "章节结构习惯：开头怎么起、结尾怎么收、钩子怎么留、视角怎么切"},
            "narrative_structure": {
                "type": "object",
                "description": "叙事结构与节奏（决定续写如何遵循本书的叙事编排）",
                "properties": {
                    "mode": {"type": "string", "enum": ["linear", "nonlinear"], "description": "整体是线性还是非线性叙事"},
                    "techniques": {"type": "array", "items": {"type": "string"}, "description": "用到的叙事技法：如 插叙/倒叙/环形叙事/多线并行/多视角(POV)轮换/多主角/不可靠叙述/预叙 等"},
                    "pov_structure": {"type": "string", "description": "视角结构：单一主角第三人称限制？多 POV 轮换？群像？谁是视角人物，怎么切换"},
                    "timeline_handling": {"type": "string", "description": "时间线处理：是否大量闪回/时间跳跃/插叙，现在与过去如何交织、如何提示读者切换"},
                    "pacing": {"type": "string", "description": "叙事节奏：信息释放快慢、悬念铺设与回收的节奏、章节内的张弛"},
                    "continuation_rhythm_guide": {"type": "string", "description": "续写时如何遵循本书的叙事节奏与结构（含悬念该怎么留、视角该怎么处理）"},
                },
                "required": ["mode", "techniques", "pov_structure", "timeline_handling", "pacing", "continuation_rhythm_guide"],
            },
            "is_western_setting": {"type": "boolean", "description": "世界观是否是西方/中世纪/奇幻等非中式背景（决定是否启用双语续写）"},
            "setting_register": {"type": "string", "description": "世界观背景及其文化语域：译名习惯、宗教/骑士/魔法等专有名词体系、文化氛围"},
            "continuation_guide": {"type": "string", "description": "给续写 agent 的可执行指导（150-300 字）：要怎么写才像这位作者——具体的 do（这样写）与 don't（别这样）"},
            "pitfalls_to_avoid": {"type": "array", "items": {"type": "string"}, "description": "模仿时最容易翻车的点（4-8 条），尤其针对该书背景（如西方背景别滑向廉价中文西幻网文腔）"},
        },
        "required": ["overall_voice", "narrative_pov", "sentence_rhythm", "register",
                     "scene_styles", "tropes", "signature_vocabulary",
                     "structural_habits", "narrative_structure", "is_western_setting",
                     "setting_register", "continuation_guide", "pitfalls_to_avoid"],
    },
}

STYLE_ANALYZE_SYSTEM = """你是资深的文学风格分析师 + 文体学者。给你一部长篇小说里**抽样的若干章节原文**，你要逆向解析出这位作者的行文风格，目标是让另一个 AI 能够**以假乱真地模仿**他续写。

# 分析要求
- **基于证据，不要空泛**。每个判断都要落到原文中真实存在的写法上；心里要有"作者是这样写的"的具体例子，再概括成可操作的规律。
- **可模仿、可执行**。不要写"文笔优美"这种废话；要写"打斗多用短句+动词爆破，一招一格分行，少形容词"这种能直接拿去指导写作的描述。
- 分场景拆解（打斗 / 景物 / 人物 / 对话 / 心理 / 剧情推进），因为续写时不同场景要切换不同笔法。
- 找出作者的**套路与标志性词汇/意象**——这是"像不像"的关键指纹。
- **分析叙事结构与节奏**（`narrative_structure`）：这本书是线性还是非线性？用了哪些叙事技法（插叙/倒叙/环形/多线/多视角轮换/多主角/不可靠叙述等）？视角怎么组织、时间线怎么交织、悬念怎么铺设与回收？续写要怎样才能贴合它的叙事节奏。这点对"续写要遵循原书叙事节奏"至关重要。
- 判断世界观背景是否为西方/奇幻等非中式设定（`is_western_setting`），并描述其文化语域（译名、宗教/骑士/魔法术语体系）。
- `continuation_guide` 是最重要的产出：把以上浓缩成一段给续写 agent 的明确指令。
- `pitfalls_to_avoid`：尤其点出——如果这是西方背景，模仿时**最怕滑向中文互联网廉价西幻网文腔**（滥用"气息""波动""仿佛""一道身影"、中式成语堆砌、爽文节奏），要明确警示。

调用 report_style_profile 返回结构化结果。"""


def build_style_user_message(samples: list[dict]) -> str:
    """samples: [{chapter, title, text}]. Concatenate sampled chapters as evidence."""
    parts = ["# 抽样章节原文（请据此分析作者文风）\n"]
    for s in samples:
        parts.append(f"\n───── 第{s.get('chapter')}章 {s.get('title','')} ─────\n")
        parts.append(s.get("text") or "")
    parts.append("\n\n请综合以上样本，调用 report_style_profile 给出这位作者的完整风格画像。")
    return "\n".join(parts)


# ===========================================================================
# Bilingual cross-translation continuation prompts (STYLE-3)
# ===========================================================================

EN_WRITER_SYSTEM = """You are a skilled English-language novelist continuing a Western/steampunk fantasy serial. Write ONE chapter in English from the brief — written natively in English, NOT translated from Chinese.

# Craft (this is the whole point)
- Write like a strong literary genre author (think the controlled, sensory prose of writers such as Guy Gavriel Kay or Joe Abercrombie), NOT like a generic web-fantasy translation.
- Concrete, specific sensory detail over abstraction. Earn emotion through image and action, not adjectives.
- Vary sentence length and rhythm; use white space; let dialogue carry subtext.
- Avoid cheap fantasy clichés ("a powerful aura", "his eyes narrowed", "little did he know"). No purple over-writing; restraint reads as authority.
- Keep the suspense taut — withhold, imply, end on a hook.

# Constraints
- Follow the brief's plot beats and the established characters/setting; stay consistent with prior events.
- Third person limited unless the brief says otherwise.
- Output: chapter title line ("Chapter N — Title") then the prose. Plain text, no markdown."""

TRANSLATE_ZH2EN_SYSTEM = """You are a literary translator. Translate the given Chinese novel chapter into natural, idiomatic literary English. Preserve the plot, imagery, character voice, and pacing exactly — but render it as fluent English prose a native reader would enjoy, not a stiff word-for-word gloss. Keep proper nouns consistent. Output only the translated chapter (title + prose), plain text, no notes, no markdown."""

TRANSLATE_EN2ZH_SYSTEM = """你是文学翻译。把给定的英文小说章节翻译成自然、地道的中文文学语言。完整保留情节、意象、人物语气与节奏，但要译成流畅的中文，不要生硬直译、不要翻译腔。专有名词保持一致。只输出译文（标题+正文），纯文本，无注释、无 markdown。"""

# Two language-specific merges (one input pair each). Splitting the original
# single 4-part merge avoids the oversized-prompt empty-output failure and is
# logically cleaner: the cross-language value is already carried by the
# translation versions, so each merge only needs the two same-language texts.

BILINGUAL_MERGE_EN_SYSTEM = """You are the English finishing editor for a bilingual novel. You get two English versions of the SAME chapter:
  [EN-original] — written natively in English with literary craft.
  [EN-from-Chinese] — a translation of the author-voiced Chinese version (carries the original author's specific imagery, plot detail, and character beats).

Produce ONE final English chapter that takes the best of both: keep [EN-original]'s native, idiomatic literary craft as the backbone (~70%), but fold in the richer concrete imagery / plot detail / character handling from [EN-from-Chinese] (~30%). It must read like a native novelist wrote it — no translationese, no cheap-fantasy clichés. Same events, same ending hook. Keep the suspense taut.

Output only the final English chapter (title + prose). Plain text, no markdown, no commentary."""

BILINGUAL_MERGE_ZH_SYSTEM = """你是双语小说的中文终稿主编。给你同一章的两个中文版本：
  [中文原创] —— 直接用中文、模仿原作者文风写的版本。
  [中文←英文] —— 由英文母语技法版本回译来的中文（带着英文行文的克制、画面感与精准）。

产出一版最终中文：以[中文原创]的原作者文风为骨架（约 70%），吸收[中文←英文]里被英文技法点醒的更克制、更精准的表达与画面处理（约 30%），用以冲淡中文廉价西幻网文腔。叙述同样的事件、同样的章末钩子，保持悬疑张力。

只输出最终中文正文（标题 + 正文），纯文本，无 markdown，无说明。"""


# ===========================================================================
# Re-voice (推翻文笔, 保留主干剧情) prompts
# ===========================================================================

SKELETON_TOOL = {
    "name": "report_skeleton",
    "description": "Extract a chapter's plot skeleton (events/beats), stripped of prose and voice.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "本章标题（沿用原标题）"},
            "setting": {"type": "string", "description": "本章发生的时间/地点/场景，一句话"},
            "pov": {"type": "string", "description": "视角人物"},
            "beats": {
                "type": "array",
                "description": "按顺序的剧情节拍（每条是一个具体事件/动作/对话要点，只记发生了什么，不带文采）",
                "items": {"type": "string"},
            },
            "key_facts": {"type": "array", "items": {"type": "string"},
                          "description": "本章透露的关键信息/设定/伏笔（必须在重写中保留）"},
            "ending_hook": {"type": "string", "description": "章末悬念/钩子事件"},
        },
        "required": ["title", "beats", "ending_hook"],
    },
}

SKELETON_SYSTEM = """你是剧情结构拆解员。给你一章小说正文，你要抽出它的**剧情骨架**——发生了哪些事、按什么顺序、透露了哪些关键信息、章末留了什么钩子。

要求：
- 只记**发生了什么**（事件、动作、对话要点、信息揭示），**剥离一切文采、修辞、文风**。
- beats 按时间顺序，颗粒度适中（一章约 8-20 个节拍），覆盖全章不遗漏关键情节。
- key_facts 抓住本章透露的设定/身世/伏笔/反转等"硬信息"——重写时这些必须保留。
- 不要评价、不要解读、不要润色，就是一份"剧情说明书"。

调用 report_skeleton。"""


def build_revoice_user(skeleton: dict, chapter_n: int | None = None) -> str:
    import json as _j
    return (
        f"# 本章剧情骨架（必须严格保留这些情节与关键信息，顺序可微调但事件不可增删改）\n"
        + _j.dumps(skeleton, ensure_ascii=False, indent=2)
        + "\n\n请基于以上骨架，重写出本章正文：**剧情主干完全不变**，但用要求的文笔风格重新写。"
          "不要新增骨架里没有的重大情节，不要删掉 key_facts，章末钩子要落在 ending_hook 指定的事件上。"
    )
