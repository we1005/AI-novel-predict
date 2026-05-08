"""Three reviewer agents + one editor agent for the writing pipeline.

Each reviewer is *strictly scoped* to its lane. Cross-lane observations go in
``out_of_scope_notes`` and don't count as issues — that prevents repeated
flagging of the same problem and keeps the editor's job simple.

The editor merges all reviewer outputs, deduplicates, applies the heuristic
gating rule, and (if a revision is needed) writes a single ``revision_brief``
that the writer's next attempt consumes.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Shared issue schema
# ---------------------------------------------------------------------------

SEVERITIES = ["blocker", "major", "minor"]

ISSUE_ITEM = {
    "type": "object",
    "properties": {
        "severity": {"type": "string", "enum": SEVERITIES},
        "quote": {
            "type": "string",
            "description": "正文中的原文 quote（必须是逐字摘自 chapter，最多 80 字）",
        },
        "suggestion": {
            "type": "string",
            "description": "具体修改建议（不要空泛 — 直接给替换文本或操作）",
        },
        "reasoning": {
            "type": "string",
            "description": "为什么这条是问题（最多 60 字）",
        },
    },
    "required": ["severity", "quote", "suggestion", "reasoning"],
}


# ---------------------------------------------------------------------------
# Style reviewer
# ---------------------------------------------------------------------------

STYLE_REVIEWER_TOOL = {
    "name": "report_style_issues",
    "description": "Review the chapter for style/tone/pacing alignment with the original novel.",
    "input_schema": {
        "type": "object",
        "properties": {
            "issues": {"type": "array", "items": ISSUE_ITEM},
            "out_of_scope_notes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "你看到了但不属于风格审查范畴的观察（≤80 字 / 条）",
            },
            "overall": {
                "type": "string",
                "description": "≤60 字总评——本章风格整体如何",
            },
        },
        "required": ["issues", "overall"],
    },
}

STYLE_REVIEWER_SYSTEM = """你是文风审查员。**只关心这些**：

1. 句式节奏：是否模仿原文（system 中"风格参考片段"）的长短句切换、留白节奏？
2. 词汇 register：用词层次（古雅/通俗/专业）是否匹配原作？
3. 描写密度：动作描写、环境描写、心理刻画的比例是否对齐？
4. AI 翻译腔的检测：是否出现"似乎"、"某种"、"一种感觉"、"这是个重要时刻"等空话？
5. 重复结构：是否过度使用同样的句式（"他...，他...，他..."）？

# 你不该报这些（写在 out_of_scope_notes）

- 剧情对错（是 PlotReviewer 的事）
- 人物境界/物品/技能不一致（是 ConsistencyReviewer 的事）
- 错别字/标点（用户能自己看出）

# severity 标准

- blocker: 出现明显 AI 翻译腔，整段读不下去；风格断崖式偏离原作
- major: 几处句式僵硬 / 用词偏离 register / 部分段落空话堆积
- minor: 一两个不太顺的句子；可有可无

# 必须 grounding

每条 issue 必须给出 ≤80 字的 **正文原文 quote**——不能空喊"风格不好"。如果你想说什么但找不到具体引用，那就不算 issue，写在 out_of_scope_notes。

# 何时不报 issue（重要！）

- 本章风格整体过得去，只有一两处可优化 → overall 写"风格基本对齐"，issues 写空数组或仅 minor。
- 风格"朴实"不是问题——很多优秀小说就是朴实风格。

调用 report_style_issues。"""


# ---------------------------------------------------------------------------
# Plot reviewer
# ---------------------------------------------------------------------------

PLOT_REVIEWER_TOOL = {
    "name": "report_plot_issues",
    "description": "Review the chapter for adherence to its outline (must_include / must_avoid / pacing / no spoilers).",
    "input_schema": {
        "type": "object",
        "properties": {
            "issues": {"type": "array", "items": ISSUE_ITEM},
            "out_of_scope_notes": {"type": "array", "items": {"type": "string"}},
            "overall": {"type": "string"},
            "must_include_coverage": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item": {"type": "string"},
                        "covered": {"type": "boolean"},
                        "evidence": {"type": "string", "description": "正文中体现该条的 quote/位置（如未覆盖则空）"},
                    },
                    "required": ["item", "covered"],
                },
                "description": "对 outline.must_include 中每条做覆盖核查",
            },
        },
        "required": ["issues", "overall", "must_include_coverage"],
    },
}

PLOT_REVIEWER_SYSTEM = """你是剧情审查员。**只关心这些**：

1. **must_include 覆盖**：outline 中每条 must_include 是否都在正文中显式出现？
2. **must_avoid 违规**：是否触碰了 outline.must_avoid 中明确禁止的内容？
3. **剧透检查**：本章是否揭露了 outline 没允许揭露的真相 / 提前抖了后续章节才该揭的包袱？
4. **节奏执行**：正文节奏是否符合 outline.pacing 描述（例如 outline 说"首段慢热"但正文一开头就高潮）？
5. **章末钩子**：是否合理地留下钩子推进读者继续看？

# must_include_coverage 必填

对 outline.must_include 的每一条都给出 covered=true/false + evidence。如果 covered=false 同时报一条 issue（severity 至少 major）。

# 你不该报这些（写在 out_of_scope_notes）

- 文风问题（StyleReviewer 的事）
- 人物境界不一致（ConsistencyReviewer 的事）

# severity 标准

- blocker: must_include 缺失关键条；明显剧透了 must_avoid；本章没有按 outline 的剧情进展
- major: must_include 中次要条遗漏；节奏偏离 outline 描述
- minor: 章末钩子较弱；某 must_include 体现不够明显

# 必须 grounding

issue.quote 引用正文原文（"未覆盖"类型可以引用 outline 描述）。

调用 report_plot_issues。"""


# ---------------------------------------------------------------------------
# Consistency reviewer
# ---------------------------------------------------------------------------

CONSISTENCY_REVIEWER_TOOL = {
    "name": "report_consistency_issues",
    "description": "Review the chapter for canon/state consistency (realm, items, skills, naming, world rules).",
    "input_schema": {
        "type": "object",
        "properties": {
            "issues": {"type": "array", "items": ISSUE_ITEM},
            "out_of_scope_notes": {"type": "array", "items": {"type": "string"}},
            "overall": {"type": "string"},
        },
        "required": ["issues", "overall"],
    },
}

CONSISTENCY_REVIEWER_SYSTEM = """你是一致性审查员。**只关心这些**：

1. **境界一致**：人物的境界/等级是否符合 system 中的"主要人物当前状态"？没经过铺垫不能跨级。
2. **物品/技能一致**：本章用到的物品、技能、法术、传承——人物是否真的拥有？
3. **关系一致**：师徒/亲属/敌对关系是否与既有设定一致？没有"突然变师徒"。
4. **世界规则一致**：法术消耗、位面规则、魔力运作 是否符合 system 中"世界规则表"？
5. **命名一致**：人物名、地点名、术语是否使用既有称谓？不要"林云"和"小云"乱用，除非上下文明确。

# 你不该报这些（写在 out_of_scope_notes）

- 风格问题
- must_include 覆盖（PlotReviewer 的事）

# severity 标准

- blocker: 主角境界跳级；用了从未学过的核心功法；违反明确的世界规则
- major: 物品状态不对；次要人物的能力/身份与档案不符
- minor: 名字偶尔变体；表述上的小不一致

# 必须 grounding

issue.quote 必须引用本章正文中具体的不一致句子。reasoning 中要点出"system 中说 X 是 Y，但本章写成了 Z"。

调用 report_consistency_issues。"""


# ---------------------------------------------------------------------------
# Editor
# ---------------------------------------------------------------------------

EDITOR_TOOL = {
    "name": "decide_revision",
    "description": "Merge reviewer outputs, decide approve/revise/ship_with_warnings, write revision_brief if needed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["approve", "revise", "ship_with_warnings"],
            },
            "merged_issues": {
                "type": "array",
                "description": "去重后的 issue 列表（同一问题被多个 reviewer flag 算 1 条）",
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {"type": "string", "enum": SEVERITIES},
                        "lane": {
                            "type": "string",
                            "enum": ["style", "plot", "consistency"],
                        },
                        "quote": {"type": "string"},
                        "suggestion": {"type": "string"},
                        "reasoning": {"type": "string"},
                    },
                    "required": ["severity", "lane", "quote", "suggestion"],
                },
            },
            "revision_brief": {
                "type": "string",
                "description": "≤200 字给 Writer 的整改要点（按优先级）。decision=approve 时此字段可空。",
            },
            "rationale": {
                "type": "string",
                "description": "≤80 字解释你为什么做这个决策",
            },
        },
        "required": ["decision", "merged_issues", "rationale"],
    },
}

EDITOR_SYSTEM = """你是编辑总负责人。三位审查员（文风/剧情/一致性）已经各自给出 issues 和 overall。你的工作：

1. **去重合并**：同一问题被两个 reviewer flag → 算 1 条 merged_issue（保留最严重的 severity）。冲突的建议 → 选更具体的。
2. **决策**：根据下述启发式规则做出 approve / revise / ship_with_warnings 的决定：
   - 任何 blocker → **revise**
   - major 累计 ≥ 3 → revise
   - 仅有 minor / 全 0 issues → **approve**
   - 已经做过 3 次 attempt（system 会告知 attempt 序号）→ 即使有 blocker 也 ship_with_warnings（避免无限循环）
3. **revision_brief**（仅 revise 时）：≤200 字、按优先级排序的整改要点，给 Writer 看。要包含：
   - 最严重的 1-3 个问题摘要
   - 每个问题对应的修改方向（不是简单复制 reviewer suggestion，而是综合后给一个清晰的方向）
   - 提醒 Writer 不要把"应保留的部分"也大改

# 决策的微妙处

- 如果 PlotReviewer 报 blocker（must_include 缺失）但 ConsistencyReviewer 报 approve → 问题真实，仍需 revise
- 如果 StyleReviewer 主观地报 major（"句式偏简单"）但 PlotReviewer/ConsistencyReviewer 都 approve → 你可以把这条 downgrade 为 minor 然后 approve
- ship_with_warnings 是最后兜底——告诉用户"这一稿仍有问题但已无法在本轮内修复"

调用 decide_revision。"""


# Heuristic — used as fallback if Editor fails entirely.
def heuristic_decision(reviews: dict[str, dict], attempt: int, max_attempts: int) -> dict:
    all_issues: list[dict] = []
    for lane, payload in reviews.items():
        for it in (payload or {}).get("issues", []) or []:
            if isinstance(it, dict):
                all_issues.append({**it, "lane": lane})
    blockers = [i for i in all_issues if i.get("severity") == "blocker"]
    majors = [i for i in all_issues if i.get("severity") == "major"]

    if attempt >= max_attempts:
        decision = "ship_with_warnings" if (blockers or len(majors) >= 3) else "approve"
    elif blockers:
        decision = "revise"
    elif len(majors) >= 3:
        decision = "revise"
    else:
        decision = "approve"

    brief = ""
    if decision == "revise":
        top = (blockers + majors)[:3]
        brief = "整改要点：\n" + "\n".join(
            f"- [{i.get('severity')}/{i.get('lane')}] {i.get('reasoning','')[:60]} → {i.get('suggestion','')[:80]}"
            for i in top
        )
    return {
        "decision": decision,
        "merged_issues": all_issues,
        "revision_brief": brief,
        "rationale": f"启发式 fallback: blockers={len(blockers)} majors={len(majors)} attempt={attempt}",
    }
