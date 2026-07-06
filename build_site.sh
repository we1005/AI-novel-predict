#!/usr/bin/env bash
# 一键重建墨笔合并站:构建 landing-app 落地页 → 同步进 结果/(阅读站 read/ 与根配置不动)。
# 用法:  ./build_site.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "▶ 构建落地页(landing-app)…"
( cd landing-app && env -u NODE_OPTIONS npm run build )

echo "▶ 同步产物 → 结果/(保留 read/ / netlify.toml / README.md)…"
rsync -a --delete \
  --exclude 'read/' \
  --exclude 'netlify.toml' \
  --exclude 'README.md' \
  --exclude '.DS_Store' \
  landing-app/dist/ 结果/

echo "✓ 完成。结果/ 已更新(read/ 未动)。"
echo "  本地预览:  cd 结果 && python3 -m http.server 8099"
echo "  部署:      netlify deploy --prod --dir=结果"
