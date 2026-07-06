# 墨笔书阁 · 天之炽 静态阅读站

纯静态网站(HTML/CSS/原生 JS),零构建,可直接部署到 Netlify。

## 结构
- `index.html` — SPA 外壳(hash 路由)
- `assets/` — 样式与脚本
- `data/books.json` — 书架索引
- `data/tianzhichi/meta.json` — 简介 + 大纲 + 目录(toc)
- `data/tianzhichi/ch/<章号>.json` — 每章正文(中文)

## 页面
1. 书架首页(书脊封面)→ 2. 书籍简介(剧情/大纲/原著 vs 续写)→ 3. 阅读页(左目录右正文)

## 本地预览
    python3 -m http.server 8099   # 然后打开 http://localhost:8099

## 部署到 Netlify
- 方式A:把本文件夹直接拖到 Netlify「Deploy」拖拽区即可。
- 方式B:连 Git 仓库,Publish directory 设为本文件夹(netlify.toml 已设 publish=".")。
