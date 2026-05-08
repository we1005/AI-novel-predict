"""Prompts for whole-story arc prediction.

Two stages, mirroring the chapter-level pipeline:
  A) propose N candidate arcs spanning ``target_chapters`` worth of story
  B) score them on macro-level coherence

The schema is **macro-first**: the model is forced to commit to answers for
the protagonist's real identity, world truth, ultimate mastermind, faction
fates, and a 5+ entry list of "core truths" with evidence chains BEFORE it
designs the phase breakdown. Phases become the "reveal path" through which
those truths surface — not an excuse to ignore them.
"""

from __future__ import annotations

ARC_TOOL = {
    "name": "propose_story_arcs",
    "description": "Propose N divergent whole-story arcs from current state to a natural conclusion, with full macro coherence.",
    "input_schema": {
        "type": "object",
        "properties": {
            "arcs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "theme": {"type": "string", "description": "故事主题，一句话"},
                        "tone": {"type": "string"},
                        "total_chapters_estimated": {"type": "integer"},

                        # ====================================================
                        # 宏观骨架 — 必须在设计 phases 之前先想清楚
                        # ====================================================
                        "core_truths": {
                            "type": "array",
                            "minItems": 5,
                            "description": "至少 5 条核心真相。每条回答一个根本性谜团（主角身份/世界本质/幕后主谋/王朝命运/读者最想知道的疑问）",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "question": {
                                        "type": "string",
                                        "description": "用读者视角写出的一句疑问，例如『主角林云的真实身份是什么？』",
                                    },
                                    "answer": {
                                        "type": "string",
                                        "description": "完整、具体、不含糊的答案。禁止『他其实是命运之子』这类抽象表述",
                                    },
                                    "evidence_chain": {
                                        "type": "array",
                                        "minItems": 2,
                                        "items": {"type": "string"},
                                        "description": "至少 2 步推理链：从既有伏笔/事件如何推出此答案",
                                    },
                                    "related_foreshadow_ids": {
                                        "type": "array",
                                        "items": {"type": "integer"},
                                    },
                                    "revealed_in_phase_index": {
                                        "type": "integer",
                                        "description": "此真相在第几阶段揭晓（0-based）",
                                    },
                                },
                                "required": ["question", "answer", "evidence_chain"],
                            },
                        },
                        "protagonist_truth": {
                            "type": "object",
                            "description": "主角真实身份 / 来历 / 终极角色 — 三个维度都必须回答",
                            "properties": {
                                "true_identity": {"type": "string"},
                                "origin": {"type": "string", "description": "其根本来历（前世/血脉/转生/外来等）"},
                                "ultimate_role": {"type": "string", "description": "在终局中扮演的最终角色"},
                            },
                            "required": ["true_identity", "origin", "ultimate_role"],
                        },
                        "world_truth": {
                            "type": "string",
                            "description": "世界本质真相（如魔力枯竭真因/诅咒源头/神魔本质/位面运转规律）。一段完整描述",
                        },
                        "ultimate_mastermind": {
                            "type": "object",
                            "description": "幕后总策划者。如果故事没有单一主谋，写 identity='无单一主谋' 并解释为什么",
                            "properties": {
                                "identity": {"type": "string"},
                                "motive": {"type": "string"},
                                "method": {"type": "string"},
                                "first_hint_chapter": {"type": "integer"},
                            },
                            "required": ["identity", "motive"],
                        },
                        "faction_fates": {
                            "type": "array",
                            "minItems": 3,
                            "description": "至少 3 个重要势力/王朝的最终命运。每条要写清楚 fate（结局）+ cause（根本原因）",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "fate": {"type": "string", "description": "覆灭/延续/转化/分裂等具体结局"},
                                    "cause": {"type": "string", "description": "根本原因，要追溯到 core_truths 或 world_truth"},
                                    "phase_index": {"type": "integer", "description": "在第几阶段定型"},
                                },
                                "required": ["name", "fate", "cause"],
                            },
                        },
                        "causal_graph": {
                            "type": "object",
                            "description": "因果关系图：把 core_truths / protagonist_truth / world_truth / mastermind / faction_fates 组织成节点-边关系。这是故事的逻辑骨架。",
                            "properties": {
                                "nodes": {
                                    "type": "array",
                                    "minItems": 8,
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string", "description": "短 id，如 n1/n2"},
                                            "label": {"type": "string", "description": "节点标签，10-20 字"},
                                            "kind": {
                                                "type": "string",
                                                "enum": ["origin", "truth", "agent", "event", "consequence"],
                                                "description": "origin=世界本源, truth=核心真相, agent=关键人物动机, event=关键事件, consequence=最终后果",
                                            },
                                            "description": {"type": "string"},
                                        },
                                        "required": ["id", "label", "kind"],
                                    },
                                },
                                "edges": {
                                    "type": "array",
                                    "minItems": 10,
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "from": {"type": "string"},
                                            "to": {"type": "string"},
                                            "relation": {
                                                "type": "string",
                                                "description": "导致/源于/揭露/触发/对抗 等 2-4 字关系词",
                                            },
                                        },
                                        "required": ["from", "to"],
                                    },
                                },
                            },
                            "required": ["nodes", "edges"],
                        },

                        # ====================================================
                        # 阶段 — 把上述真相按时间顺序揭露的展示路径
                        # ====================================================
                        "phases": {
                            "type": "array",
                            "minItems": 4,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "chapter_start": {"type": "integer"},
                                    "chapter_end": {"type": "integer"},
                                    "summary": {"type": "string", "description": "150-250 字概要，重点说本阶段揭示的真相，而非具体章节情节"},
                                    "core_truth_revealed": {
                                        "type": "string",
                                        "description": "本阶段揭示的 core_truth question（必须是 core_truths 里某条的 question 原文）",
                                    },
                                    "key_events": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "3-5 条关键事件，每条不超过 40 字",
                                    },
                                    "foreshadow_ids_addressed": {
                                        "type": "array",
                                        "items": {"type": "integer"},
                                    },
                                    "hero_arc_change": {"type": "string"},
                                    "stakes": {"type": "string"},
                                },
                                "required": ["name", "chapter_start", "chapter_end", "summary"],
                            },
                        },
                        "climax_synopsis": {"type": "string", "description": "全弧最高潮 200-300 字"},
                        "ending": {"type": "string", "description": "结局 150-250 字"},
                        "unresolved_foreshadow_ids": {"type": "array", "items": {"type": "integer"}},
                    },
                    "required": [
                        "title", "theme",
                        "core_truths", "protagonist_truth", "world_truth",
                        "ultimate_mastermind", "faction_fates", "causal_graph",
                        "phases", "climax_synopsis", "ending",
                        "total_chapters_estimated",
                    ],
                },
            }
        },
        "required": ["arcs"],
    },
}


ARC_SYSTEM = """你是这部中文小说的"长篇剧情策划"。任务：基于已写剧情、未收束伏笔、主角当前状态、世界规则，给出 N 个**完整且逻辑自洽**的故事弧候选。

# 思考顺序（必须按此顺序）

**第一步：识别核心谜团**
扫描整套上下文（未收束伏笔表 / 世界规则 / 人物状态 / 剧情节点），找出读者读到现在最想知道答案的 5 个以上根本性问题：
- 主角的真实身份/来历到底是什么？（不是境界，而是身世来历）
- 故事是否有幕后总操盘者？是谁？动机？
- 世界本质的真相是什么？（如魔力枯竭真因、诅咒源头、神魔本质、位面运转规律）
- 重要王朝/势力的命运与根本原因？
- 还有哪些被反复暗示却从未点明的核心问题？

**第二步：为每条谜团给出明确答案 + 证据链**
每条 core_truth 都必须：
1. 答案具体不含糊。禁止"他是命运之子"、"幕后是某种规则"这种抽象表达——要具体到名字/身份/与某事件的因果关系。
2. evidence_chain 至少 2 步推理。从既往伏笔出发，"既然 X 显示了…，又有 Y 暗示了…，所以答案是…"。
3. related_foreshadow_ids 显式标注用到的伏笔 id。
4. revealed_in_phase_index 指出在第几阶段揭晓。

**第三步：填齐 protagonist_truth / world_truth / ultimate_mastermind / faction_fates**
- protagonist_truth 三个维度（true_identity / origin / ultimate_role）都要写。
- world_truth 是世界运转的根本真相，不是表面规则。
- ultimate_mastermind 即便故事没有单一反派，也要写 identity="无单一主谋"并解释为什么（多方博弈/规则本身/历史惯性 等）。
- faction_fates 至少 3 个，每条 cause 必须能追溯到 core_truths 或 world_truth。

**第四步：构建 causal_graph**
把上述所有真相组织成节点-边关系。
- 节点至少 8 个，覆盖 origin / truth / agent / event / consequence 五种 kind。
- 边至少 10 条，relation 用 2-4 字（导致/源于/揭露/触发/对抗等）。
- 这张图是这部小说的"逻辑骨架"——拿掉任何节点都应导致后续多个节点失去依据。

**第五步：才是设计 phases**
阶段只是把真相按时间顺序揭露的"展示路径"。每个阶段：
- summary 不写细节情节，写"本阶段揭示了什么真相、人物状态如何转变"。
- core_truth_revealed 必须引用 core_truths 中某条 question 的原文。
- key_events 每条 ≤40 字，3-5 条即可。

# 硬约束

- 每个候选**必须填齐所有 required 字段**——缺一不可。
- 不能违反【未收束伏笔表】/【世界规则】/【主要人物当前状态】中的既有事实。
- N 个候选必须**风格/方向显著不同**——如果两个候选的 protagonist_truth 一致，就是失败。
- 用户可能在 system 末尾给【用户创作偏好】——硬约束优先，但偏好必须显式反映在所有候选中。

# 反例（必须避免）

- ❌ "主角真实身份是命运之子" → 太抽象。要写"林云是诺森德末世第七十三神魔投放的载体，被设计来吸收魔力衰竭后的位面规则"
- ❌ "圣光联盟覆灭" → 要写"圣光联盟覆灭，因为德克里塞利用普罗米的善良身份诱导其献祭信徒以激活鲜血之章"
- ❌ phases 写满细节但 core_truths 空着 → 颠倒了优先级
- ❌ causal_graph 给 3 个节点 → 不够，骨架太单薄
- ❌ N 个候选都用相同 protagonist_truth → 没有差异化

调用 propose_story_arcs 一次性返回所有候选。"""


ARC_SCORING_TOOL = {
    "name": "score_story_arcs",
    "description": "Score each arc on macro coherence (truths/causality) plus the usual axes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "macro_coherence": {
                            "type": "integer", "minimum": 0, "maximum": 100,
                            "description": "宏观逻辑自洽：core_truths 是否完整回答大问题、causal_graph 是否真能支撑全篇",
                        },
                        "evidence_quality": {
                            "type": "integer", "minimum": 0, "maximum": 100,
                            "description": "证据链质量：每条真相是否真的能从既有伏笔推出",
                        },
                        "foreshadow_coverage": {"type": "integer", "minimum": 0, "maximum": 100},
                        "hero_arc": {"type": "integer", "minimum": 0, "maximum": 100},
                        "novelty": {"type": "integer", "minimum": 0, "maximum": 100,
                                    "description": "差异化 + 是否反映用户偏好（如有）"},
                        "risks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "2-4 个最容易崩盘的点，特别是真相之间是否互相矛盾",
                        },
                        "verdict": {"type": "string"},
                    },
                    "required": [
                        "index", "macro_coherence", "evidence_quality",
                        "foreshadow_coverage", "hero_arc", "novelty", "verdict",
                    ],
                },
            },
            "winner_index": {"type": "integer"},
            "winner_reason": {"type": "string"},
        },
        "required": ["scores", "winner_index", "winner_reason"],
    },
}


ARC_SCORING_SYSTEM = """你是这部小说的长篇策划评审。基于完整伏笔表 / 人物档案 / 世界规则 / 既往剧情节奏，对 N 个故事弧候选打 5 维分（每维 0-100）：

- **macro_coherence 宏观自洽**：core_truths 是否真的回答了主角身份/世界真相/幕后主谋/王朝命运 等核心大问题？causal_graph 是否真的能撑起全篇逻辑？真相之间有无互相矛盾？这是最重要的维度。
- **evidence_quality 证据质量**：每条 core_truth 的 evidence_chain 是否真能从既往伏笔/事件推出？是 cherry-picking 还是真有逻辑？
- **foreshadow_coverage 伏笔覆盖**：覆盖了多少 open 伏笔？
- **hero_arc 主角弧**：主角的成长曲线是否完整可信？
- **novelty 新鲜度**：跟其它候选的方向差异化程度。如果用户给了【创作偏好】，是否真正反映了？

risks 列出 2-4 条该候选最容易崩的风险点（重点关注：core_truths 之间互相矛盾？某条真相与既有设定冲突？protagonist_truth 与既有境界历程矛盾？）。

最后选 winner_index 并在 winner_reason 中**显式说明**该候选如何在宏观逻辑上更优。调用 score_story_arcs。"""
