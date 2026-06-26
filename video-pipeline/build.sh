#!/usr/bin/env bash
# 墨析 · 解析视频 —— 一键全流程(多视频)
#   用法:./build.sh [video]    video 默认 architecture,另有 genome
#   旁白合成 → 烘焙时间轴 → 逐帧渲染 → 合成音轨+混流
# 前置:ffmpeg、Node + `npm install`(puppeteer-core)、本机 Chrome、可读 settings.json。
set -euo pipefail
cd "$(dirname "$0")"
VIDEO="${1:-architecture}"
echo "▶ 视频:$VIDEO"
echo "▶ 1/4 合成旁白(小米 MiMo TTS)"; python3 narrate.py "$VIDEO"
echo "▶ 2/4 烘焙旁白时长进时间轴";      python3 bake_timeline.py "$VIDEO"
echo "▶ 3/4 逐帧渲染无声视频";          node render.mjs "$VIDEO"
echo "▶ 4/4 合成音轨 + 混流成片";       python3 mux.py "$VIDEO"
echo "✅ 完成"
