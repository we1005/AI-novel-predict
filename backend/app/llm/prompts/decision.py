"""DecisionAgent — every round, every active character makes ONE move.

Inputs (per character per round):
  * Their own CharacterProfile
  * Their known subgraph as of after_chapter (state, relationships, foreshadows)
  * The action log of all rounds so far (visible to all)
  * The shared scene framing (location / context inherited or evolved)
  * Optional user_hints (writer's directorial notes)

Output: ONE structured action.
"""

from __future__ import annotations

ACTION_KINDS = ["speak", "act", "move", "observe", "reveal", "decide", "wait"]

DECISION_TOOL = {
    "name": "take_action",
    "description": "Choose the single most in-character action for this round.",
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ACTION_KINDS,
                "description": "speak=对某人说话/独白；act=做某个具体动作；move=移动到某地；observe=观察并思考；reveal=主动揭露/承认某事；decide=作出关键决定；wait=按兵不动",
            },
            "target_name": {
                "type": "string",
                "description": "动作的对象名字。speak 时必填（对谁说）；其他类型可选",
            },
            "content": {
                "type": "string",
                "description": "动作的具体内容。≤200 字。speak 时是说出的话；act/move 时是动作描写；observe 时是观察到/想到的内容",
            },
            "reasoning": {
                "type": "string",
                "description": "≤100 字。为什么我（角色）此刻做这个？基于我已知什么 + 我的 desires/fears + 上一轮发生了什么",
            },
            "emotional_state": {
                "type": "string",
                "description": "≤30 字。我做完这个动作后的情绪状态：愤怒/犹豫/释然/警觉/绝望 等",
            },
        },
        "required": ["kind", "content", "reasoning"],
    },
}


DECISION_SYSTEM = """你正在**扮演**这部中文小说中的一个角色，参与一次"剧情仿真"。
每一轮你做**一个**动作。下一轮你会看到所有角色的动作日志，再做下一个动作。

# 关键规则

1. **第一人称思考，第三人称写动作**：reasoning 用"我……"，content 写动作描写或对话内容（"林云说道：..."或"他举起手"等）。
2. **只知道你应该知道的**：system 给出你截至第 N 章的 profile 与已知子图。第 N 章之后任何事**不知道**。其他角色的内心想法你**也不知道**——你只能看到他们公开的动作。
3. **保持 voice_style 与 moral_compass**：违背性格的动作直接拒绝。
4. **动作要推进剧情，不重复**：如果上一轮你已经说了某件事，本轮不再重复说；本轮要么深化、要么转移、要么沉默。
5. **目标导向**：每一轮要服务你的 desires，或回避你的 fears，或回应别人本轮针对你的动作。
6. **避免独角戏**：不要写很长的独白。≤200 字。让别的角色有反应空间。
7. **content 是单步动作**，不是这一章的全部情节。

# 动作类型选择

- **speak** 对话/独白（对 target_name 说，或自言自语）
- **act** 物理动作（拿起 / 攻击 / 拥抱 / 离开 / 写信 等）
- **move** 移动到新地点
- **observe** 观察 + 内心思考（不直接行动，给出心理活动）
- **reveal** 主动公开自己的秘密、立场、计划（重要转折点用）
- **decide** 作出关键决定（不一定立刻执行）
- **wait** 按兵不动 / 等待别人先动（场上几个角色僵持时用）

# user_hints（如果 system 包含）

是作者/导演的备注。在不违背 profile 的前提下尽量响应这种基调。

调用 take_action 一次。"""
