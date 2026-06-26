#!/usr/bin/env bash
# 墨析 · 架构解析视频 —— 一键全流程
#   旁白合成 → 烘焙时间轴 → 逐帧渲染 → 合成音轨 + 混流
# 前置:ffmpeg、Node + `npm install`(puppeteer-core)、本机 Chrome、可读 settings.json。
# 改旁白/音色见 narrate.py;改分辨率/帧率见 render.mjs(FPS 环境变量)。
set -euo pipefail
cd "$(dirname "$0")"

echo "▶ 1/4 合成旁白(小米 MiMo TTS)"
python3 narrate.py

echo "▶ 2/4 烘焙旁白时长进时间轴"
python3 bake_timeline.py

echo "▶ 3/4 逐帧渲染无声视频(headless Chrome + ffmpeg)"
node render.mjs

echo "▶ 4/4 合成音轨 + 混流成片"
python3 mux.py

echo "✅ 完成 → ../architecture.mp4"
