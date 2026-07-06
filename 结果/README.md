# 墨笔 · 合并静态站(结果/)

一个可整体部署的纯静态文件夹:落地页在根,阅读站在 `read/` 子目录,**全相对路径**。

## 结构
- `index.html` · `assets/` · `favicon-*.png` · `brush-logo.png` — 落地页(由 `../landing-app` 构建)
- `read/` — 墨笔书阁·天之炽 阅读站(零构建 SPA,`index.html` + `assets/` + `data/`)
- `netlify.toml` — 发布配置(publish=".")

落地页的「读续写的《天之炽》」按钮相对链到 `./read/`。

## 本地预览(阅读站靠 fetch 读 data,必须走 http,不能 file:// 直接打开)
    cd 结果 && python3 -m http.server 8099
    # 落地页 http://localhost:8099/   阅读站 http://localhost:8099/read/

## 重建落地页(不动 read/)
    ./build_site.sh            # 见项目根;构建 landing-app 并同步进本文件夹

## 部署 Netlify
    netlify deploy --prod --dir=结果
