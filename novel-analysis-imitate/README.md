# novel-analysis-imitate

中文中长篇「深度分析 + 跨书仿写/重组」引擎。设计见 `分析和设计.md`。

- 形态:独立 FastAPI(端口 8100)+ Next.js(待建)。
- 复用:把同仓库 `../backend` 当包 import(`naimitate/bootstrap.py`),零改现有续写项目;
  成员书原始抽取/风格/笔法直接复用 `backend/data/books/<slug>/novel.db`,settings 共享。
- 启动后端:`backend/run.sh`(复用 backend 的 .venv)。
- 现状:Phase 0 脚手架(/health /books /projects)+ project.db。
  Phase 1(进行中):多书深度分析地基(chapter_beat 等新分析层 + 可视化)。
