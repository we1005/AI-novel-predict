# 实验:数字占比 vs 自然语言

支撑文档 [`../数字vs自然语言-为何不是过度设计.md`](../数字vs自然语言-为何不是过度设计.md) 的可复现脚本与原始结果。

度量沿用 `naimitate/analysis/_fingerprint.py` 的确定性正则(弱断言 `HEDGE`、词汇 `str.count`),
**不依赖 LLM 评委**;生成用小米 mimo-v2.5,API key 从仓库根 `backend/data/settings.json`(已 gitignore)读取,脚本不含密钥。

| 脚本 | 内容 | 结果 |
|---|---|---|
| `numexp.py`  | 第一轮 · 开环,2 轴(弱断言/词汇密度)× 3 档 × 3 样本,数字设定 vs 自然语言档位 | `numexp_results.json` |
| `numexp2.py` | 第二轮 · 闭环纠偏,同一超标初稿用数字反馈 vs 自然语言反馈改写(目标 5/千字) | `numexp2_results.json` |
| `numexp3.py` | 第三轮 · 开环确认,弱断言 6 样本,数字 vs 尽力校准的自然语言(steelman) | `numexp3_results.json` |

```bash
# 在仓库根执行
backend/.venv/bin/python novel-analysis-imitate/docs/experiments/numexp.py
backend/.venv/bin/python novel-analysis-imitate/docs/experiments/numexp2.py
backend/.venv/bin/python novel-analysis-imitate/docs/experiments/numexp3.py
```

> 注:温度 0.9 + 小样本,结果有噪声;复跑数值会有出入,但三轮的定性结论(数字在 prompt 侧不被精确兑现、
> 自然语言粗粒度分档至少相当、数字价值在测量侧)稳定可重现。详见支撑文档第八节"适用边界"。
