# novel-analysis-imitate(墨析)

中文中长篇「深度分析 + 跨书仿写/重组」引擎。设计见 `分析和设计.md`。

- 形态:独立 FastAPI(端口 8100)+ Next.js(端口 3200)。
- 复用:把同仓库 `../backend` 当包 import(`naimitate/bootstrap.py`),零改现有续写项目;
  成员书原始抽取/风格/笔法直接复用 `backend/data/books/<slug>/novel.db`,settings 共享。

## 启动

后端(复用 backend 的 .venv):
```
cd novel-analysis-imitate/backend
PYTHONPATH=. ../../backend/.venv/bin/python -m uvicorn naimitate.main:app --host 0.0.0.0 --port 8100
```
前端:
```
cd novel-analysis-imitate/frontend
npm install && npm run dev   # http://localhost:3200,/api/* 自动代理到 :8100
```

## Phase 1 · 多书深度分析地基(已完成)

5 个分析层,逐章/逐事件抽取 + 聚合卡,存进每本书 novel.db 的新表;前端 5 维度可视化。
- **chapter_beat** 逐章节拍:张力/场景类型/POV/plot_function/章末钩子 → 张力曲线 + 节奏卡
- **worldview_reveal** 世界观揭示:铺垫手法/信息倾倒率/埋设跨度/前置密度 → 江南式铺垫量化
- **relationship_event** 关系演变:状态转变轨迹 → 每对关系时间线
- **golden_finger_step** 金手指台阶:升级斜率/触发分布/对手差距
- **pov_event** 视角调度:从 beat 派生(零额外 LLM)→ 切换时间轴

API:`POST /books/{slug}/analyze`(全层/指定层)、`GET /books/{slug}/analysis`(汇总)、
`POST /projects/{slug}/analyze`(对成员书串行跑)。

## Phase 2+ · 生成用例(已落地 compose 地基 + UC1/2/3/4)

统一收敛到:**compose 虚拟书 → set_active → OutlineRun(承载新故事大纲)→ draft.write_chapter**。
- compose 默认 `voice_only` 模式:只搬运源书的 StyleProfile(含 scene_exemplars)+ 26 类笔法卡,
  **不带**源书章节/实体/FTS,从而「有 A 的声音、不串 A 的剧情」。`full` 模式整库克隆(续写 A 自身)。
- **UC2** `POST /compose/uc2`:用 voice_source 文风写用户逐章大纲。
- **UC1** `POST /compose/uc1`:克隆主声音 + overlay 多书融合文风摘要,写自创剧情。
- **UC4** `POST /compose/uc4`:在文风之上按 technique_template 逐章注入节奏/POV/铺垫约束。
- **UC3** `POST /compose/uc3`:抽取 plot_sources 的去设定剧情母核 → 重锚定到 anchor_world → 用 voice_source 文风生成。
- 生成:`POST /compose/{cslug}/generate`(后台逐章);导出:`GET /compose/{cslug}/export`。

## 模型

复用主项目 settings.json 的 FAST/STRONG lane(当前切到小米 MiMo:fast=mimo-v2.5、strong=mimo-v2.5-pro)。
分析层走 FAST,生成走 STRONG。
