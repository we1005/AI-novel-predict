"""Prompts for the craft-snippet library (09-笔法片段库与拆解).

两段式:
  - TAG:便宜模型扫一批章节原文,抽出 MVP 三类笔法片段(打斗/潜台词对话/章节钩子)。
  - CARD:强模型对某一类的片段做风格拆解,产一张可拼进 writer system 的「笔法卡」。
均走 JSON-in-text(贴 schema + json_repair),不用 forced tool_choice。
"""

from __future__ import annotations

import json

# MVP 三类(及细分)
CRAFT_CATEGORIES = {
    # 动作
    "combat": "打斗/战斗片段。subtype: duel(单挑) / melee(数人混战) / war(大规模战争/军阵调度)",
    "chase": "追逐/潜行/逃亡片段。",
    "ritual": "法术/异能/仪式/异象展示片段。",
    # 对话
    "dialogue_subtext": "潜台词/留白型对话——话少、不说透、靠留白让读者自己想,符合人物身份。",
    "dialogue_group": "群戏多人对话交锋(三人以上、机锋往来)。",
    "monologue": "独白 / 内心独白 / 旁白。",
    # 描写
    "scene_env": "景物/环境描写(天气、季节、时辰、地貌、氛围)。",
    "scene_place": "场所/建筑/空间描写(城池、宫阙、营帐、室内)。",
    "appearance": "人物出场/外貌描写(标志性外貌细节)。",
    "object": "服饰/器物/兵器描写。",
    "sensory": "通感 / 气味 / 声音 / 触觉等感官描写。",
    # 情绪心理
    "interior": "内心戏/心理活动写法(间接暗示为主)。",
    "emotion_peak": "情绪爆发场景(决绝/悲恸/暴怒/狂喜)。",
    "lyrical": "抒情 / 感伤 / 咏叹段落。",
    "flashback": "回忆 / 闪回的切入与收束。",
    # 结构功能
    "hook": "章节钩子。subtype: opening(开篇抓人) / ending(章末留悬念引下章)",
    "transition": "转场 / 时间跳跃 / 视角切换的过渡写法。",
    "suspense": "悬念的埋设与回收(铺垫—兑现)。",
    "climax": "高潮 / 反转的构造。",
    # 世界观质感
    "worldbuild": "设定的『非信息倾倒式』引入(不靠大段交代就把设定喂给读者)。",
    "in_world_text": "史书腔 / 典籍 / 传说 / 谶语等书中文本引文。",
    "culture": "文化 / 民俗 / 制度的侧写。",
    # 作者签名
    "signature_metaphor": "标志性比喻 / 意象的用法。",
    "motif": "复现母题(反复出现的意象,如槿花/棉布娃娃)。",
    "rhythm": "句式节奏样本(短句堆叠 / 长句铺陈的典型段)。",
    "anti_trope": "反套路 / 反类型(反网文、反爽点)的笔法。",
}

CATEGORY_IDS = list(CRAFT_CATEGORIES)


CRAFT_TAG_TOOL = {
    "name": "tag_craft_snippets",
    "input_schema": {
        "type": "object",
        "properties": {
            "snippets": {
                "type": "array",
                "description": "从本批章节原文中摘出的笔法片段(只摘真正典型的,可为空数组)。",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "enum": CATEGORY_IDS},
                        "subtype": {"type": "string", "description": "combat: duel/melee/war ; hook: opening/ending ; 其余类可空"},
                        "chapter_number": {"type": "integer", "description": "该片段所属章节号(必须是本批给定的章节号之一)"},
                        "excerpt": {"type": "string", "description": "原文片段,**逐字摘抄**,80-400 字;保留原作语感,不要改写/缩写"},
                        "representativeness": {"type": "integer", "minimum": 0, "maximum": 100, "description": "典型性:多大程度代表作者该类笔法的水准(越高越适合做范文)"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "2-5 个细粒度标签(如 短句堆叠/通感/留白/反转钩)"},
                    },
                    "required": ["category", "chapter_number", "excerpt", "representativeness"],
                },
            }
        },
        "required": ["snippets"],
    },
}


# strict-安全版 schema(供 response_format=json_schema 用):去掉火山 strict 不支持的
# minItems/minimum/maximum;所有字段进 required + additionalProperties:false。
CRAFT_TAG_STRICT_SCHEMA = {
    "type": "object",
    "properties": {
        "snippets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": CATEGORY_IDS},
                    "subtype": {"type": "string"},
                    "chapter_number": {"type": "integer"},
                    "excerpt": {"type": "string"},
                    "representativeness": {"type": "integer"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["category", "subtype", "chapter_number", "excerpt", "representativeness", "tags"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["snippets"],
    "additionalProperties": False,
}


def craft_tag_response_format() -> dict:
    return {"type": "json_schema",
            "json_schema": {"name": "craft_tag", "strict": True, "schema": CRAFT_TAG_STRICT_SCHEMA}}


_CAT_LIST_FOR_PROMPT = "\n".join(f"- {cid}:{desc}" for cid, desc in CRAFT_CATEGORIES.items())

CRAFT_TAG_SYSTEM = f"""你是中文小说的"笔法标注员"。给你若干章原文,请摘出其中**真正典型**的各类笔法片段,逐字摘抄(不改写)。

# 可选类别(category 只能取下列 id 之一)
{_CAT_LIST_FOR_PROMPT}

# 硬约束
- excerpt **必须逐字摘抄原文**(80-400 字),不要改写、缩写、拼接。
- category 必须是上面列出的 id;combat 用 subtype duel/melee/war,hook 用 subtype opening/ending,其余类 subtype 可留空字符串。
- chapter_number 必须是本批给定的章节号之一。
- **宁缺毋滥**:只摘真正能当"范文"的典型片段;平庸的、过渡性的不摘。同一段落只归最贴切的一类,不要重复摘。一批摘 0-15 条均可。
- representativeness 据"多能代表作者该类最高水准"打分(0-100)。

调用 tag_craft_snippets 返回。"""


def build_tag_user(chapters: list[dict]) -> str:
    """chapters: [{chapter, title, text}]"""
    parts = [f"【第{c['chapter']}章 {c.get('title','')}】\n{c['text']}" for c in chapters]
    nums = "、".join(str(c["chapter"]) for c in chapters)
    return (f"以下是第 {nums} 章的原文。请摘出其中各类典型笔法片段,逐字摘抄。\n\n"
            + "\n\n".join(parts))


CRAFT_CARD_TOOL = {
    "name": "craft_style_card",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "一句话概括作者这一类笔法的总体特征"},
            "sentence_rhythm": {"type": "string", "description": "句长分布 / 短句堆叠 vs 长句铺陈 / 停顿与标点习惯"},
            "rhetoric_density": {"type": "string", "description": "比喻/通感/排比等修辞的频率与偏好"},
            "pov_person": {"type": "string", "description": "视角与人称习惯"},
            "info_pacing": {"type": "string", "description": "信息释放速度:慢热/碎匀/爆发"},
            "signature_vocab": {"type": "array", "items": {"type": "string"}, "description": "该类高频词/意象"},
            "structure_template": {"type": "string", "description": "典型 起-承-收 模板(一两句)"},
            "do": {"type": "array", "items": {"type": "string"}, "description": "写这类时该做的要点"},
            "dont": {"type": "array", "items": {"type": "string"}, "description": "该避免的写法"},
        },
        "required": ["summary", "sentence_rhythm", "do", "dont"],
    },
}


CRAFT_CARD_SYSTEM = """你是中文小说的"笔法分析师"。给你某位作者某一类笔法(如打斗/潜台词对话/章节钩子)的若干真实片段,请拆解出可复用的写作范式,供续写 agent 照此模仿。

# 要求
- 基于给定片段归纳,不要泛泛而谈;句式/修辞/节奏/信息释放要具体到"作者怎么做的"。
- do / dont 要可执行(能直接写进写作指令),dont 针对"模仿这类时最易写坏的点"。
- 只输出 JSON 对象,不要其它文字、不要 markdown 围栏。严格符合给定 schema。"""


def build_card_user(category: str, snippets: list[dict]) -> str:
    desc = CRAFT_CATEGORIES.get(category, category)
    body = "\n\n".join(f"【片段{i+1}·第{s.get('chapter_number')}章·{s.get('subtype') or ''}】\n{s.get('excerpt','')}"
                       for i, s in enumerate(snippets))
    return (f"# 类别\n{category}:{desc}\n\n# 该类真实片段({len(snippets)} 条)\n\n{body}\n\n"
            "请拆解出这一类的写作范式。")


def schema_hint(tool: dict) -> str:
    return ("\n\n# 输出格式(严格 · 覆盖任何「调用工具」指示)\n"
            "只输出一个 JSON 对象,不要其它文字/围栏,严格符合此 JSON Schema:\n"
            + json.dumps(tool["input_schema"], ensure_ascii=False))
