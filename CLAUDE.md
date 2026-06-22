# 项目记忆 · 墨笔 (AI 小说续写)

## 交流规则
- **始终用中文回复用户**（包括状态汇报、进度、结论；代码注释/commit 也以中文为主）。不要夹用整段英文。

## 提交规则
- 用户已授权：**直接提交并推送到 `main` 分支**（不开 feature 分支）。
- 提交前必查不带入密钥/隐私：`.env`、`backend/data/settings.json`、`backend/data/`(含 novel.db) 均已 gitignore。
- commit/PR 尾部署名：`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。

## 服务 / 启动
- 后端：`backend/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`（venv 的 uvicorn shebang 已坏，必须 `python -m`）。
- 前端：`cd frontend && npm run dev`（端口 3100）。

## 架构要点（详见 墨笔-agent架构设计docs/ 与 墨笔-改进记录与架构.md）
- 多服务商：火山引擎 Coding-Plan + 阿里 DashScope，按任务路由：结构化→doubao-seed-2.0-code，散文→minimax-m3，快审/抽取→doubao-seed-2.0-lite / qwen3.5-flash。
- **结构化输出一律 JSON-in-text（贴 schema + json_repair），不用 forced tool_choice**——doubao 系大上下文下强制工具会静默吞输出。
- 整本续写链路：arc 骨架 → 整本推演(落 per-phase OutlineRun) → write-book(逐章成稿 → 写→回灌记忆反馈环 → 阶段复审 + 人审 gate → 续写)。
