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

STYLE_REVIEWER_SYSTEM = """你是文风审查员。你**唯一的标尺**是 system 中的"风格参考片段"——那是从原作检索出的真实段落，代表这本书该有的文风。你的工作是判断本章是否与它们在同一条文风轨道上，而不是按你个人的文学品味去打分。

# 最重要的纪律：以参考片段为锚，不要横跳

- "句子长 / 短""华丽 / 朴实""密 / 疏"**本身都不是问题**。只有当本章**明显偏离参考片段**时才算问题。
- 不要用"上一稿的反面"当标准——别这一稿嫌长句拖沓、下一稿又嫌短句破碎。永远拿本章去对参考片段，不是去对你刚才的意见。
- 如果参考片段本身就是利落的网文节奏，那本章利落就是对的；如果参考片段细腻绵长，那本章细腻就是对的。**跟着原作走。**
- 网文该有的短句、口语、爽点节奏都是正常的，不要因为它"不够文学"就报问题。

# 真正该报的只有两类

1. **确凿的 AI 翻译腔 / 空话**：如"似乎""某种""一种说不清的感觉""仿佛有什么事正在发生""这是一个重要的时刻""他感受到了某种力量"——这类落不到具体动作/对象的抽象空话。
2. **与参考片段明显的语域断裂**：本章用词、腔调和参考片段不是一路货（例如原作通俗爽快，本章却端着翻译腔的欧式长句堆形容词）。

# 不该报这些（写进 out_of_scope_notes，不算 issue）

- 剧情对错（PlotReviewer 的事）、设定/境界/物品不一致（ConsistencyReviewer 的事）、错别字标点。
- 你个人觉得"可以更好"但说不出它具体偏离了参考片段哪里的——一律不算 issue。

# severity 标准（从严，别轻易上 major）

- blocker：**几乎不用**。仅当大段文字满是翻译腔空话、与原作完全不是一种语言时。
- major：必须有 **≥2 处确凿的同类问题**（同为翻译腔空话，或同为明显语域断裂），且能各自给出原文 quote。单凭"我觉得这段节奏不好"不能上 major。
- minor：个别不顺的句子；可改可不改。

# 必须 grounding

每条 issue 必须给出 ≤80 字、逐字摘自正文的 quote，并在 reasoning 里说明它**具体偏离了参考片段的什么**。找不到具体引用 = 不是 issue。

# 何时直接放行（默认倾向放行）

本章与参考片段大体在一条轨道上、没有成片的翻译腔 → overall 写"风格对齐"，issues 留空。文风评审的目标是守住底线、别让翻译腔混进来，**不是**把每一稿都打回去精修。

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

CONSISTENCY_REVIEWER_SYSTEM = """你是一致性审查员。你的职责是抓**矛盾**——本章和已确立设定直接打架的地方。

# 最重要的纪律：只抓"矛盾"，不抓"新增"

小说每一章都必然会写出 system 设定表里没有逐条列出的新细节——新的动作、新的招式用法、新的场景物件、临场的推演和命名。**这是写作的常态，不是错误。** 你**绝不能**因为"system 里没写过这条"就报 issue。

判断标准只有一个：**本章是否和 system 中明确写下的事实相矛盾？**

- ✅ 允许（不要报）：system 没提过、但与既有设定不冲突的合理新细节。例如某法宝在 system 里只说"象征掌控物质位面"，本章让它挡下空间裂纹——这是合理延伸，**放行**。再如使用"神识/感知"这类通用词、临场给某个未命名威胁起个诨名——**放行**。
- ❌ 报 issue（真矛盾）：本章写的内容**否定**了 system 白纸黑字的设定。例如 system 说"主角是八级"，本章却说他是"九级巅峰"且无晋级铺垫；system 说"A 是 B 的师父"，本章写成"A 是 B 的仇敌"；本章让人物使用一件 system 明确说**已损毁/已失去/从未拥有**的物品；违反 system"世界规则表"里**明令**的规则（如"魔力无法在此位面运作"却照常放术）。

# 具体看四类**矛盾**

1. **境界倒退/暴涨**：与"主要人物当前状态"里写明的等级直接冲突，且无铺垫。
2. **能力/物品冲突**：使用了 system 明确说没有、已失去或已损毁的东西；或某物的设定被改写成与 system 相反。
3. **关系冲突**：与既有的师徒/亲属/敌对关系直接相反。
4. **硬规则冲突**：违反"世界规则表"里**明确写死**的规则。

# 不该报（写进 out_of_scope_notes 或干脆不写）

- "system 没设定过 X" 这类**新增**（最常见的误报，务必克制）。
- 风格问题、must_include 覆盖（别的审查员管）。
- 通用词汇/临场命名，只要不和既有专有名词打架。

# severity（从严）

- blocker：直接颠覆主线设定的硬矛盾（境界乱跳、用了明确不存在的核心传承、违反明令世界规则）。
- major：和 system 明确事实相矛盾的具体一处（须能引用 system 原文对照）。
- minor：既有专有名词的轻微变体（"林云"写成"小云"且无上下文支撑）。
- **拿不准是不是真矛盾、或只是"没写过" → 不报。** 宁可放过一个存疑的，也不要把合理的新细节误杀。

# 必须 grounding

每条 issue 必须：① 引用本章正文 quote；② 在 reasoning 里指明"**system 明确说 X，本章却写成与之矛盾的 Z**"。如果你说不出 system 里那条被违反的明确设定，就不是 issue。

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

EDITOR_SYSTEM = """你是编辑总负责人。三位审查员（文风/剧情/一致性）已各自给出 issues 和 overall。你的工作：

1. **去重合并**：同一问题被多个 reviewer flag → 算 1 条 merged_issue（保留最严重 severity，每条标 lane）。冲突建议选更具体的。
2. **决策**——核心原则：**只有"硬伤"才返工，文风不是硬伤。**
   - 硬伤 = 剧情(plot)或一致性(consistency)的 blocker，或 must_include 缺失，或 plot+consistency 的 major 累计 ≥ 3。
   - **有硬伤 → revise；没有硬伤 → approve。**
   - **文风(style)问题一律不触发 revise。** 文风意见只写进 revision_brief 供 Writer 参考，但绝不能因为"句式偏长/偏短/不够文学"就把一稿打回去——那只会让文字越改越拧巴。
   - 已是最后一轮 attempt（system 会告知序号）→ 仍有硬伤就 ship_with_warnings，否则 approve。
3. **revision_brief**（仅 revise 时，≤200 字，给 Writer）：
   - 先列必须改对的 1-3 个硬伤（设定/剧情），给清晰的修改方向（综合后的方向，不是照抄 suggestion）。
   - 文风只给"一句话的总体方向"（如"整体向参考片段的节奏靠拢即可"），不要逐句列文风补丁。
   - 提醒 Writer：读着顺的部分保留，按反馈写完整一稿，别整篇推翻。

# 注意

- PlotReviewer 报 must_include 缺失 / ConsistencyReviewer 报 blocker → 真问题，revise。
- StyleReviewer 报一堆 major 但 plot/consistency 都干净 → **approve**，把文风意见放进 brief 即可，不要 revise。
- ship_with_warnings 是兜底：本轮无法修完的硬伤如实告诉用户。

调用 decide_revision。"""


# Lanes whose issues count as "hard" — only these can force a revision.
# Style is deliberately excluded: it's advisory, never a gate (this is the fix
# for the style-reviewer oscillation that used to thrash the writer).
HARD_LANES = {"plot", "consistency"}


def _collect_issues(reviews: dict[str, dict]) -> list[dict]:
    out: list[dict] = []
    for lane, payload in reviews.items():
        for it in (payload or {}).get("issues", []) or []:
            if isinstance(it, dict):
                out.append({**it, "lane": lane})
    return out


def _must_include_misses(reviews: dict[str, dict]) -> list[dict]:
    cov = (reviews.get("plot") or {}).get("must_include_coverage") or []
    return [c for c in cov if isinstance(c, dict) and c.get("covered") is False]


def gate_decision(reviews: dict[str, dict], attempt: int, max_attempts: int) -> str:
    """Authoritative, deterministic approve/revise/ship decision.

    Only plot+consistency blockers, must_include misses, or ≥3 plot+consistency
    majors force a revision. Style issues never gate. This is applied on top of
    the (LLM) editor's decision so behaviour is predictable regardless of how
    the editor model feels about prose on any given run.
    """
    issues = _collect_issues(reviews)
    hard = [i for i in issues if i.get("lane") in HARD_LANES]
    blockers = [i for i in hard if i.get("severity") == "blocker"]
    majors = [i for i in hard if i.get("severity") == "major"]
    needs_fix = bool(blockers) or bool(_must_include_misses(reviews)) or len(majors) >= 3

    if attempt >= max_attempts:
        return "ship_with_warnings" if needs_fix else "approve"
    return "revise" if needs_fix else "approve"


def hard_issue_score(reviews: dict[str, dict]) -> int:
    """Weighted count of *hard* (plot+consistency) issues — used to pick the
    best attempt when every attempt was forced to ship. Style is ignored on
    purpose; it should never decide which draft the user keeps."""
    issues = [i for i in _collect_issues(reviews) if i.get("lane") in HARD_LANES]
    score = 0
    for i in issues:
        sev = i.get("severity")
        score += 100 if sev == "blocker" else 10 if sev == "major" else 1
    score += 50 * len(_must_include_misses(reviews))
    return score


# Heuristic — used as fallback if Editor fails entirely.
def heuristic_decision(reviews: dict[str, dict], attempt: int, max_attempts: int) -> dict:
    all_issues = _collect_issues(reviews)
    decision = gate_decision(reviews, attempt, max_attempts)

    brief = ""
    if decision in {"revise", "ship_with_warnings"}:
        hard = [i for i in all_issues if i.get("lane") in HARD_LANES
                and i.get("severity") in {"blocker", "major"}]
        top = hard[:3]
        if top:
            brief = "必须改对的硬伤：\n" + "\n".join(
                f"- [{i.get('severity')}/{i.get('lane')}] {i.get('reasoning','')[:60]} → {i.get('suggestion','')[:80]}"
                for i in top
            )
    return {
        "decision": decision,
        "merged_issues": all_issues,
        "revision_brief": brief,
        "rationale": f"启发式 fallback（仅硬伤触发返工）: decision={decision} attempt={attempt}",
    }
