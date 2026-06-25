# 火山引擎 结构化输出（response_format）笔记 + 本项目接入现状

> 来源:火山方舟(Ark)官方文档「JSON 结构化输出」。本文件记录其用法,以及墨笔项目
> 当前的接入方式、试点结论与后续计划。base_url:`https://ark.cn-beijing.volces.com/api/v3`。

## 一、是什么

当需要模型像程序一样输出标准 JSON(而非自然语言)时,通过请求体里的 **`response_format`**
对象约束输出。相较"用提示词反复强调要 JSON",它在**解码层**保证格式,优势:

- **输出可靠**:不会再有 ```` ```json ```` 围栏 / markdown / 散文前言 / 字段缺失。
- **提示词更简单**:不必在 prompt 里反复强调"请输出 JSON / 按如下格式"。

> 注意:该能力官方标注 **beta**,且**按模型**支持(不是所有模型都支持);低延迟在线推理不支持;
> **不要**与 `frequency_penalty` / `presence_penalty` 同用(可能输出异常)。

## 二、两种模式

### 1) `json_object`(只保证是合法 JSON,不限定结构)

```json
"response_format": { "type": "json_object" }
```
- 要求:输入(prompt)里要出现 "json" 字样(我们的 schema 提示词本就含)。
- 用途:消除围栏/markdown/前言,拿到可直接 `json.loads` 的字符串。**结构靠提示词里贴的 schema 引导**(不强制)。

### 2) `json_schema` + `strict`(连结构也保证:字段必出、类型对、顺序按 schema)

```json
"response_format": {
  "type": "json_schema",
  "json_schema": {
    "name": "my_schema",
    "strict": true,
    "schema": { "type": "object", "properties": { ... },
                "required": [...], "additionalProperties": false }
  }
}
```
- `strict: true` → 严格按 schema 生成;不支持的关键字会**显式报错**。
- 字段顺序 = schema 里同级字段的先后。

### 模式对比

| | json_schema | json_object |
|---|---|---|
| 生成合法 JSON | ✓ | ✓ |
| 限定结构(字段/类型/必填) | ✓ | ✗(仅保证合法 JSON) |
| 严格模式 strict | 支持 | 不涉及 |
| 推荐度 | 高 | 一般 |

## 三、strict 模式支持的 JSON Schema 关键字(子集!)

**支持**:`type`(integer/number/string/boolean/null/array/object)、`$ref`(仅 `#` 本地引用)、
`$defs`、`const`、`enum`、`anyOf`、`oneOf`、`allOf`;array 下 `prefixItems`/`items`/`unevaluatedItems`;
object 下 `properties`/`required`/`additionalProperties`/`unevaluatedProperties`。

**⚠️ 不在支持列表(本项目要注意)**:`minItems` / `maxItems` / `minimum` / `maximum` / `minLength` 等——
方舟会**忽略无格式约束语义的关键字**,**明确不支持的会报错**。我们现有 schema 里大量用
`minItems`/`minimum`/`maximum`(如 must_include `minItems:2`、典型性 0–100),**上 strict 前必须先裁剪**。

## 四、Schema / Prompt 设计建议(官方)

- 字段用清晰英文名 + `description`;类型贴合业务(数字别用 string)。
- 少用 `$ref`/嵌套,结构尽量一次性展开(无意义嵌套增加出错率)。
- 用 `enum` 明确枚举;`required` 列全 + 配 `"additionalProperties": false`。
- Prompt **只描述任务本身**,不要再强调"请用 JSON 输出/按某格式"(与 schema 冗余甚至冲突)。
- 推荐用 Pydantic(Python)/ Zod(TS)生成 schema,避免与代码类型不一致。

## 五、本项目接入现状(墨笔)

### 历史:我们一直用第三种做法 = JSON-in-text
早期用过 forced `tool_choice`,但 doubao 系大上下文下会静默吞输出/空(见《墨笔-改进记录与架构.md》#14/#39),
遂改为 **JSON-in-text**:把 schema 贴进 system 提示词,模型当普通文本吐 JSON,再用 `json_repair` 抢救。
代价是反复出现 ```` ```json ```` 围栏 / `**` markdown / 字段缺失 / arc 碎片化等噪声,要在前端/解析层不断打补丁。

### 现在:已接入 `response_format`(试点)
- `llm.call(..., response_format="json_object")`:**仅对火山(provider=`volc`)模型**挂
  `{"type":"json_object"}`;其它厂商不挂(走原 JSON-in-text)。
- **自动降级**:若模型不支持(create 抛含 "response_format" 的错),**去掉该参数重试一次**,回落 JSON-in-text。
- `json_repair` 仍作兜底。
- 已试点 agent:`craft.tag`、`style.analyze`。

代码位置:`backend/app/llm/client.py`(call 的 `response_format` 参数 + volc 网关 + 降级);
调用处 `backend/app/craft/pipeline.py`、`backend/app/style/pipeline.py`。

### 全模型实测支持矩阵(`scripts/probe_response_format.py`,直连 provider、绕过降级)

| 模型 | json_object | json_schema(strict) |
|---|---|---|
| **doubao-seed-2.0-pro** | ✅ 合法JSON | ✅ 合法+合规结构 |
| **doubao-seed-2.0-lite** | ✅ 合法JSON | ✅ 合法+合规结构 |
| doubao-seed-2.0-code | ❌ 400 不支持 | ❌ 400 |
| doubao-seed-code | ❌ 400 | ❌ 400 |
| deepseek-v4-pro | ❌ 400 | ❌ 400 |
| deepseek-v4-flash | ❌ 400 (`json_object is not supported by this model`) | ❌ 400 |
| minimax-m2.7 | ❌ 400 | ❌ 400 |
| minimax-m3 | ⚠ 接受但吐空(需 repair) | ⚠ 吐空 |
| glm-5.2 | ⚠ 吐空 | ❌ 400 |
| kimi-k2.6 | ⚠ 吐空 | ⚠ 带围栏 |

**结论:火山里只有 `doubao-seed-2.0-pro` / `doubao-seed-2.0-lite` 真正支持两种模式(含 strict 合规)。**
其余要么 400 拒绝(code/deepseek 系/minimax-2.7),要么接受但吐空/带围栏(minimax-m3/glm/kimi,不可靠)。

> **更正(诚实记录)**:此前曾称"deepseek-v4-flash ✅ 支持 json_object"——错。它其实 **400 拒绝**
> `response_format`;当时 `craft.tag` 看起来"干净成功",是 `llm.call` 的**自动降级**把该参数去掉、
> 退回 JSON-in-text、模型恰好吐了干净 JSON 所致,**不是 response_format 的功劳**。降级兜底有效,
> 但不能据此判定支持。

### 据矩阵收紧 client 网关
`client.py` 用**白名单** `RESPONSE_FORMAT_MODELS = {doubao-seed-2.0-pro, doubao-seed-2.0-lite}`:
只对白名单模型挂 `response_format`,避免对其它模型每次"先 400 再重试"的浪费;非白名单走 JSON-in-text。
自动降级仍保留作双保险。

## 六、后续计划(TODO)

1. 把 `json_object` 推广到其它结构化 agent:extract 各 agent、outline.refine、predict/arc。
2. 对最脆的**深嵌套 arc**(曾"碎片化")试 **`json_schema + strict`**——**先裁掉 `minItems`/`minimum`/`maximum`
   等不支持关键字**,验证火山对应模型支持后再上。
3. 多厂商差异:`json_object` 是 OpenAI 标准、DashScope(qwen)多半也支持,可逐个验证后放开 volc 之外的厂商;
   `json_schema strict` 各厂商/模型支持度不一,需逐一实测。
4. 全程保留 `json_repair` 兜底;strict 不支持的厂商/模型自动走老路。

## 七、注意事项速查

- beta,谨慎用于关键生产路径;按模型支持,先实测。
- 不与 `frequency_penalty`/`presence_penalty` 同用。
- 低延迟在线推理不支持。
- strict 关键字是子集(见 §三),上线前裁 schema。
- json_object 需输入含 "json" 字样。
