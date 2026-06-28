# genre_template · 通用类型模板(产品功能)

把 V_genre 验证过的"从同题材多书语义层抽写作配方"固化为可保存、可调用的产品功能。

## 设计依据(均已实测)
- **V_genre**:5 书语义模板 > 裸 prompt(克味/套路/新鲜三轴全胜)、≥ 贴单作者 → 值得做成正式资产。
- **V1**:题材在语义层、结构指纹=作者层 → 模板**纯语义**(不存句长/段落等结构指纹)。
- **V2**:裸取共性会更套路 → system_prompt 内建"强制求异 + 负面清单 + 保持节奏"护栏。
- **V5**:多书知识应**离线蒸成一个连贯模板**,不要写作时混入多作者生片段 → 用模板而非跨书 raw 检索。

## 数据模型(project.db · genre_template 表)
`slug / name / source_slugs / template_json / system_prompt / cost_usd / created_at / updated_at`
- `template_json`:`{imagery, motifs, worldview_lexicon, atmosphere, flavor_recipe, anti_patterns}`(纯语义部件)。
- `system_prompt`:渲染好的、可直接喂任意 writer 的指令(含求异/负面清单护栏)。

## 模块 / API
- `generate/genre_template.py`:
  - `extract_genre_template(name, source_slugs)`:多书语义层蒸馏 → 存表。
  - `render_system_prompt(template, anti_cliche=True)`:纯函数,组装 + 护栏(可单测)。
  - `preview(slug, topic)`:用模板 system_prompt 现写样例(证明可调用)。
- 端点:`POST /genre-templates/extract`、`GET /genre-templates`、`GET /genre-templates/{slug}`、
  `DELETE /genre-templates/{slug}`、`POST /genre-templates/{slug}/preview`。

## 端到端实测(已通过)
从 5 本克苏鲁维多利亚(诡秘之主/余烬之铳/诡秘地海/黎明医生/深海余烬)抽出「克苏鲁维多利亚」模板:
- 意象:蒸汽朋克都市 / 幽灵船 / 面具伪装 / 畸形肢体 / 绿色幽灵火焰 / 福尔马林遗体 / 探索者协会…
- 母题:秘密组织招募、接触禁忌致疯、身份潜入、超凡力量的代价…
- anti_patterns:把超凡力量游戏化、忽略知识本身的危险、让主角轻易获信任…(顺带实现 V4 负面清单)
- preview 现写"停尸间起伏的胸腔",自动用上"值夜者 / 诅咒人偶低语",够克味。

## 边界 / 下一步
- 已是"可保存 + 可调用"MVP(API + e2e)。**前端页**(列表/抽取/preview/编辑)未做,列为下一步。
- 未接进 compose 生成内核(写整本时自动注入 system_prompt)——可作为 outline/draft 的可选注入,后续接。
- 旋钮可控(V6/#7:风格强度/求异度滑杆)未做;模板编辑(人工增删意象/负面项)未做。
