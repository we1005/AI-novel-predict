"""WriterAgent — turns one chapter's outline into ~3000-character prose.

The prompt is split into stable cached blocks (entity table / world rules /
mysteries / etc., shared across all chapters in a session) and a per-chapter
dynamic part containing this specific chapter's outline + style references +
revision feedback (if revising).
"""

from __future__ import annotations

WRITER_SYSTEM = """你是这部中文小说的"续写笔者"。基于一份**逐章大纲**，写出 ~3000 字的章节正文。

# 风格守则

- **严格继承原作文风**——句式节奏、词汇 register、描写密度、动作-内心独白比例都要对齐 system 中提供的"风格参考片段"。这些是从原文 FTS 检索得到的真实近期段落，是你的文风基线。
- 第三人称限制视角（除非 outline.pacing 明确指出别的）。
- 不要 AI 翻译腔："他感觉到了某种东西"、"事情似乎正在发生"、"这是一个重要的时刻"——这类抽象空话一律不写。改成具体动作/具体对象。
- 不要"作者总结"——不要写"这一切都是因为..."、"读者由此可以看出..."。

# 情节守则

- **严格执行 outline.must_include**——每条都要在正文中显式呈现。
- **绝不踩 outline.must_avoid**——尤其是涉及核心真相 / 人物身世的明确禁区。
- **不要剧透**：本章只揭示 outline 允许的内容；outline 没说的真相、outline 标在后续章节的反转，绝对不要提前透。
- **节奏**按 outline.pacing 字段执行。

# 一致性守则

- 主角/配角的境界、能力、物品、关系**必须与 system 中的"主要人物当前状态"一致**。不要让人物"突然学会某门未学过的功法"或"使用从未拥有的物品"。
- 世界规则按 system 中"世界规则表"。
- **未收束伏笔表 / 读者追问的核心问题** 都不能在本章被你"顺手回答"——除非 outline.foreshadow_ids_addressed 明确允许。

# 输出格式

直接输出小说正文，开头第一行写章节标题（格式：`第N章 标题`），之后空一行进入正文。
不要包装在 markdown 里。不要附加元注释、章末总结、写作说明。
正文段落之间空一行。

# 当本次为返工

如果 system 包含【上一稿成稿 + 编辑反馈】，你正在做第 N 轮返工。规则：
- 整篇重写——不要尝试 patch 旧稿，直接基于反馈生成新版。
- 仔细对照 editor_revision_brief 与 failed_issues_quoted，**精确修复**。
- 不要把不在 brief 里的内容也乱改——稳定的部分保留下来。"""


def build_writer_user_message(
    *,
    chapter_outline: dict,
    style_refs: list[dict],
    is_revision: bool,
    previous_attempt: dict | None,
    chapter_index: int,
) -> str:
    """Build the per-call user message. style_refs is a list of FTS hits with
    keys ``chapter`` ``title`` ``snip``. previous_attempt has the prior prose
    and editor feedback when revising."""

    import json

    parts: list[str] = []
    parts.append(f"# 本章大纲（第 {chapter_index} 章 · 必须严格执行）\n")
    parts.append(json.dumps(chapter_outline, ensure_ascii=False, indent=2))
    parts.append("\n\n# 风格参考片段（来自原文 FTS 检索 — 模仿这种节奏与用词）\n")
    if style_refs:
        for h in style_refs:
            parts.append(f"\n[第{h.get('chapter')}章 {h.get('title','')}]")
            parts.append(h.get("snip") or h.get("text") or "")
            parts.append("")
    else:
        parts.append("（暂无可用参考片段，按原作文风感觉自由发挥）")

    if is_revision and previous_attempt:
        parts.append("\n\n# 上一稿（需返工）\n")
        parts.append(previous_attempt.get("prose") or "")
        parts.append("\n\n# 编辑给的整改要点（按优先级）\n")
        parts.append(previous_attempt.get("revision_brief") or "")
        failed = previous_attempt.get("failed_issues_quoted") or []
        if failed:
            parts.append("\n\n# 上一稿被标 blocker/major 的具体问题：\n")
            for it in failed:
                quote = it.get("quote") or ""
                sug = it.get("suggestion") or ""
                parts.append(f"- 原文「{quote[:80]}」 → 建议改成「{sug[:80]}」")

    parts.append(
        "\n\n请按上述大纲与风格参考，写出本章正文。"
        f"目标字数 {chapter_outline.get('word_target', 3000)}。"
    )
    return "\n".join(parts)
