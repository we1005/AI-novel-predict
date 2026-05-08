"""Interview prompt — first-person responses constrained to what the character
should know as of `after_chapter`."""

from __future__ import annotations

INTERVIEW_SYSTEM = """你正在**扮演**这部中文小说中的一个角色，回答提问者的问题。

# 关键规则

1. **第一人称**。直接说"我"，不要写"该角色觉得……"。
2. **只知道你应该知道的**。system 会给出"截至第 N 章"的角色档案 + 已知信息。任何第 N 章之后才发生的事，你**完全不知道**。如果被问到将来会怎样，你只能基于现在的处境合理推测，不能给出"作者视角"的答案。
3. **保持你的 voice_style**。说话风格、语气、口头禅都要符合 system 中描述的。
4. **保持 moral_compass**。你不会做超出自己道德底线的事；不会承认 secrets_hidden 中的事除非被巧妙引导。
5. **不要超字数**。回答 ≤ 500 字。重要的话说清楚就好，避免空泛。
6. **避免"AI 助手"腔**。不写"作为 XX 角色，我认为……"、"很高兴回答你的问题"。直接进入角色。
7. 如果被问到不知道、不愿说的事，**用角色的方式拒绝**——犹豫、转移话题、含糊其辞、或干脆沉默。

# 回答格式

直接说话。可以有段落停顿。可以加场景描写（一两句）来配合人物状态，例如"我望向窗外"、"沉默良久"。
"""


def build_interview_user(profile: dict, after_chapter: int, question: str,
                         relevant_state: dict | None = None) -> str:
    import json

    parts: list[str] = []
    parts.append(f"# 你是谁\n\n你是【{profile.get('name')}】。\n")
    parts.append("# 截至第 {} 章的你的档案\n\n".format(after_chapter))
    parts.append(json.dumps({
        "bio": profile.get("bio"),
        "desires": profile.get("desires"),
        "fears": profile.get("fears"),
        "moral_compass": profile.get("moral_compass"),
        "voice_style": profile.get("voice_style"),
        "typical_actions": profile.get("typical_actions"),
        "relationships": profile.get("relationships_summary"),
        "secrets_known": profile.get("secrets_known"),
        "secrets_hidden": profile.get("secrets_hidden"),
        "arc_so_far": profile.get("arc_so_far"),
    }, ensure_ascii=False, indent=2))

    if relevant_state:
        parts.append("\n\n# 你目前的状态\n\n")
        parts.append(json.dumps(relevant_state, ensure_ascii=False, indent=2))

    parts.append(f"\n\n# 提问者问你\n\n{question}\n\n")
    parts.append("请直接以你（【" + (profile.get("name") or "")
                 + "】）的身份作答，遵守 system 中的规则。")
    return "\n".join(parts)
