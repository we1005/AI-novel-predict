# 06 · Agent 与 Prompt 设计

> 全系统 LLM agent，按职责分层，温度与模型有规律地配置。本页是横切对照表。

> **🔄 实现现状（2026-06 更新）——下表的 model 列与"输出方式"列已过时，以当前为准：**
>
> **(A) 多服务商 + 模型路由**（`FAST`/`STRONG` 是抽象 lane，实际经路由落到具体模型）：
> | 任务类型 | 实际模型 | 服务商 |
> |---|---|---|
> | 结构化/工具 JSON（抽取、评分、骨架、去重、文风分析、预测候选、大纲、完整性裁决） | `doubao-seed-2.0-code` | 火山 |
> | 散文（成稿、双语、重写、翻译、仿真旁白） | `minimax-m3` | 火山 |
> | 快审/抽取/仿真决策（量大便宜） | `doubao-seed-2.0-lite` / `qwen3.5-flash` | 火山 / 阿里 |
>
> **(B) "输出方式"列基本作废**：除少数小上下文外，**所有结构化 agent 已从 forced tool_choice 改 JSON-in-text**（贴 schema + `json_repair` 解析正文）——doubao 系在大上下文下强制工具调用会静默吞输出。抽取 agent 保留"先 tool、空则回退 JSON-in-text"。
>
> **(C) 新增 agent**（原表未列）：`style.analyze`（文风画像）、`translate.zh2en/en2zh`、`bilingual.en_writer`、`bilingual.merge`（双语）、`revoice.skeleton` + `revoice.write.{wangwen,mimic,english}`（重写文笔）、`arc.project.judge`（整本推演完整性裁决）。每个 agent 的模型/温度/max_tokens 可在 `/settings` 按需覆盖（`AGENT_REGISTRY` + settings.json）。
>
> **(D) 通用保险**：客户端层**空输出自动重试**（无正文且无工具调用即重试，最多 3 次）。

## 1 · Agent 总名单

| # | Agent | 链路 | 文件 | model | T | 输出方式 |
|---|---|---|---|---|---|---|
| 1 | EntityAgent | 抽取 | `prompts/extraction.py::ENTITY_*` | FAST | 0.3 | tool_use |
| 2 | ForeshadowAgent | 抽取 | `extraction.py::FORESHADOW_*` | FAST | 0.3 | tool_use |
| 3 | StateAgent | 抽取 | `extraction.py::STATE_*` | FAST | 0.3 | tool_use |
| 4 | PlotAgent | 抽取 | `extraction.py::PLOT_*` | FAST | 0.3 | tool_use |
| 5 | WorldAgent | 抽取 | `extraction.py::WORLD_*` | FAST | 0.3 | tool_use |
| 6 | MysteryAgent | 抽取 | `prompts/mystery_per_batch.py` | FAST | 0.3 | tool_use |
| 7 | RelationshipAgent | 图谱 | `prompts/relationships.py` | FAST | 0.3 | tool_use |
| 8 | DivergerAgent | 预测 | `prompts/prediction.py::CANDIDATE_*` | STRONG | 0.95 | tool_use |
| 9 | ScorerAgent | 预测 | `prediction.py::SCORING_*` | STRONG | 0.2 | tool_use |
| 10 | WritingAgent (predict) | 预测 | `prediction.py::WRITING_*` | STRONG | 0.75 | stream_text |
| 11 | ArcDivergerAgent | 全弧 | `prompts/arc.py` | STRONG | 0.9 | tool_use |
| 12 | OutlineRefineAgent | 大纲 | `prompts/outline_refine.py` | STRONG | 0.6 | tool_use |
| 13 | DraftWriterAgent | 写作 | `prompts/writer.py` | STRONG | 0.75 | text |
| 14 | StyleReviewerAgent | 写作 | `prompts/reviewers.py::STYLE_*` | FAST | 0.2 | tool_use |
| 15 | PlotReviewerAgent | 写作 | `reviewers.py::PLOT_*` | FAST | 0.2 | tool_use |
| 16 | ConsistencyReviewer | 写作 | `reviewers.py::CONSISTENCY_*` | FAST | 0.2 | tool_use |
| 17 | EditorAgent | 写作 | `reviewers.py::EDITOR_*` | FAST | 0.2 | tool_use |
| 18 | ProfileBuilderAgent | 仿真 | `prompts/profile.py` | FAST | 0.3 | tool_use |
| 19 | InterviewAgent | 仿真 | `prompts/interview.py` | FAST | 0.7 | stream_text |
| 20 | DecisionAgent | 仿真 | `prompts/decision.py` | FAST | 0.85 | tool_use |
| 21 | ReportAgent (sim) | 仿真 | `prompts/sim_report.py` | STRONG | 0.7 | text |

## 2 · 模型选型 4 条规则

```
1. 输出是结构化 JSON          → MODEL_FAST (qwen3.5-flash)
2. 输出是中文长文 ≥ 3000 字   → MODEL_STRONG
3. 需要严格遵守复杂世界规则    → MODEL_STRONG
4. 决策类（含创意但短 output）→ MODEL_FAST
```

默认 `MODEL_FAST = MODEL_STRONG = qwen3.5-flash` —— 实测 flash 在中文长文上够用。如果对质量不满，把 STRONG 切到 `qwen-max` 即可（`backend/.env::MODEL_STRONG=qwen-max`）。

## 3 · 温度梯度

```
T = 0.2  ── 评分 / 仲裁 / 评审 (Reviewer / Editor / Scorer)
T = 0.3  ── 抽取 / Profile (要稳定)
T = 0.6  ── Outline (有结构感的中度创意)
T = 0.7  ── ReportAgent / Interview (自然中文表达)
T = 0.75 ── Writer (主创作)
T = 0.85 ── DecisionAgent (角色决策要有意外)
T = 0.9  ── Arc Diverger (100 章规模发散)
T = 0.95 ── Predict Diverger (1-3 章规模发散)
```

## 4 · Prompt 五段式模板

我们的 system prompt 几乎都是这个结构：

```
1. 角色定义     (你是 XXX 的 YYY 助手)
2. 职责清单     (你的任务: 1) ... 2) ... 3) ...)
3. 硬约束       (绝对不要 ...; 必须 ...)
4. 输出规范     (调用 tool XX 返回; 字段含义 ...)
5. 失败行为     (不确定时 ...; 不存在时 ...)
```

举个例子（`ENTITY_SYSTEM` 简化版）：

```
你是中文小说的实体抽取助手。           ← 角色
任务：阅读给定章节，抽出新登场的命名实体。 ← 职责
硬约束:
  - 不要重复已在【现有实体表】中的实体    ← 缓存上下文驱动的去重
  - aliases 仅写明确化名 / 别号
  - importance 0-100 取决于 mention 频次
调用 emit_entities 返回。              ← 输出规范
若本批没有新实体，返回空 entities=[]。   ← 失败行为
```

## 5 · Tool Schema 模板

所有 tool 用 Anthropic 兼容格式（DashScope 透传）：

```python
ENTITY_TOOL = {
    "name": "emit_entities",
    "description": "Emit a list of new named entities found in this batch.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["person", "faction", "item", "location", "skill", "concept"]},
                        "name": {"type": "string"},
                        "aliases": {"type": "array", "items": {"type": "string"}},
                        "description": {"type": "string"},
                        "importance": {"type": "integer"},
                        "first_appear_chapter": {"type": "integer"},
                    },
                    "required": ["type", "name"]
                }
            }
        },
        "required": ["entities"]
    }
}
```

调用时 `tool_choice={"type": "tool", "name": tool["name"]}` 强制只能调用这个 tool——避免模型选择"不调用，直接回答"。

## 6 · Cached Block 怎么用

`backend/app/llm/client.py::cached_block(text)` 包装一段文本为 prompt cache 候选。规则：

```python
system = [
    {"type": "text", "text": AGENT_SYSTEM},      # 不缓存（每次不同）
    cached_block(stable_json(open_foreshadowings)),   # 缓存
    cached_block(stable_json(world_rules)),           # 缓存
    cached_block(stable_json(characters)),            # 缓存
]
```

注意点：
- `cached_block` 必须放在 system 数组的**靠后位置**（cache 是前缀生效）
- 内容要稳定排序（用 `stable_json` 而不是 `json.dumps`）
- 同批多 agent 用**完全相同**的 cached blocks，第一次付费，之后 `cache_read`

## 7 · 失败兜底分层

| 层 | 触发 | 兜底 |
|---|---|---|
| LLM 调用层 | API 报错 / timeout | retry 1 次后抛出 |
| Tool 解析层 | tool_use 缺字段 / schema 错 | `json_repair` 兜底解析 resp.text |
| Editor 仲裁层 | Editor 输出无 decision 字段 | `heuristic_decision()` 纯逻辑判断 |
| Pipeline 层 | 任何 agent 失败 | 写 `LLMCall.extra_json.error`，pipeline status='failed' |
| 抽取批次层 | 6 agent 中某个失败 | 不回滚已成功的，仅这一个 agent 输出空 |

## 8 · 全 prompt 索引

```
backend/app/llm/prompts/
├── arc.py                  # 全弧预测
├── decision.py             # 角色决策（仿真）
├── extraction.py           # entity / foreshadow / state / plot / world
├── interview.py            # 角色第一人称问答
├── mystery_per_batch.py    # 跨批 mystery 增量
├── outline_refine.py       # phase → 逐章大纲
├── prediction.py           # 单章 A/B/C 三段
├── profile.py              # 角色档案构建
├── relationships.py        # 关系抽取（独立链路）
├── reviewers.py            # style/plot/consistency 三审 + editor
├── sim_report.py           # 仿真 → 章节正文
└── writer.py               # 写作 Writer
```

## 9 · 调试 / 审计

每个 agent 调用都写 `LLMCall` 表：

```sql
SELECT agent, COUNT(*), AVG(elapsed_ms),
       SUM(input_tokens), SUM(output_tokens), SUM(cost_usd)
FROM llm_call
GROUP BY agent
ORDER BY 6 DESC;
```

前端 `/monitor` 页可视化最近 168 小时的 cost 与失败率。`extra_json` 字段保存 cache hit ratio、retry 次数、tool name 等。

---

文档结束。回到 → [00-总览](./00-总览.md)
