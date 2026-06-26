# 解析视频合成管线

> 位置:仓库根 `video-pipeline/`。一套脚本按 `specs.json` 里的 **video key** 产出多支视频:
> `architecture`(系统架构)与 `genome`(文风基因组 · 七层结构与公式)。
> 动画源与成片都在 `novel-analysis-imitate/docs/`(`<video>-video.html` / `<video>.mp4`)。

把 `../novel-analysis-imitate/docs/architecture-video.html`(时间驱动的 GSAP 动画)
合成为带中文旁白解说的 MP4(`../novel-analysis-imitate/docs/architecture.mp4`)。旁白用小米 MiMo TTS(`mimo-v2.5-tts`,白桦音色)合成,
渲染借鉴 [nexu-io/html-video](https://github.com/nexu-io/html-video) 的 Hyperframes
范式 —— 单文件动画 HTML → headless Chrome 逐帧定格 → ffmpeg 编码,但直接用本机系统
Chrome 跑通,无需自行 build 那个 TS monorepo。

## 思路

视频 HTML 暴露三个钩子供逐帧渲染:`window.__ready` / `window.__duration` /
`window.__seek(t)`。master timeline 用 `gsap.timeline({paused:true})`,渲染器按
`t = 帧号 / fps` 单调递增地 `__seek` 后截图,因此进度条、计数器等回调按序触发、可定格。

关键设计:**视频节奏由旁白时长驱动**。每幕在屏停留 = 前导 `LEAD` + 该幕旁白时长 +
收尾 `TAIL`,幕间交叠 `XF`。旁白先合成、量出每段时长,再烘焙进 HTML 的 `NARR[]`,
HTML 内部据此推算各幕起止;`mux.py` 用相同公式把每段旁白 `adelay` 到对应时刻拼成音轨。

## 四步管线

| 步骤 | 脚本 | 作用 |
| --- | --- | --- |
| 1 | `narrate.py [video]` | 取 `specs.json` 该视频的解说词 → MiMo TTS → `_build/<video>/seg*.wav` + `durations.json` |
| 2 | `bake_timeline.py [video]` | 把旁白时长写进该视频 HTML 的 `const NARR=[...]` |
| 3 | `render.mjs [video]` | headless Chrome 逐帧截图 → ffmpeg → `_build/<video>/silent.mp4`(无声) |
| 4 | `mux.py` | 按各幕时刻 `adelay+amix` 合成音轨 → 与无声视频混流 → `architecture.mp4`(产物在 novel-analysis-imitate/docs/) |

`check.mjs` 是可选的快速校验:全量渲染(数千帧、数分钟)前,先确认 `__ready`、
`__duration`、无 `pageerror`,并抽几帧到 `_build/check_*.png` 肉眼核对。

## 前置依赖

- **ffmpeg**(`ffmpeg` / `ffprobe` 在 PATH 中)
- **Node**:`npm install`(装 `puppeteer-core`;`node_modules/` 已 gitignore)
- **本机 Chrome**:默认 macOS 路径;其他平台用环境变量 `CHROME=/path/to/chrome` 覆盖
- **API Key**:`narrate.py` 只从 `backend/data/settings.json`(仓库根,已 gitignore)
  的 `providers.xiaomi` 读取 `api_key`/`base_url`,**不硬编码、不写进任何产物**。
  也可用 `MOBI_SETTINGS=/path/to/settings.json` 覆盖。
- 纯 Python 标准库(`narrate.py`/`bake_timeline.py`/`mux.py` 无需第三方包)

## 用法

```bash
cd video-pipeline      # 仓库根目录下
npm install            # 仅首次:装 puppeteer-core
./build.sh architecture   # 系统架构视频 → ../novel-analysis-imitate/docs/architecture.mp4
./build.sh genome         # 文风基因组视频 → ../novel-analysis-imitate/docs/genome.mp4
# 省略参数默认 architecture
```

或分步(都接 `[video]`):`python3 narrate.py genome` → `python3 bake_timeline.py genome` →
`node render.mjs genome` → `python3 mux.py genome`。

## 自定义

- **改旁白文字**:编辑 `specs.json` 里对应视频的 `narr` 数组(顺序对应各幕)。改完重跑该视频全流程即可。
- **加一支新视频**:在 `specs.json` 加一个 key(html/out/voice/timing/narr),配一个时间驱动的 `*-video.html`(暴露 `__seek/__duration/__ready` 钩子)即可复用全套脚本。
- **换音色**:`TTS_VOICE=苏打 python3 narrate.py`(可选 mimo_default / 冰糖 / 茉莉 /
  苏打 / 白桦 / Mia / Chloe / Milo / Dean)。
- **改帧率**:`FPS=24 node render.mjs`。
- **改节奏常数**:`LEAD`/`TAIL`/`XF` 三处必须同步 —— `architecture-video.html`
  时间轴块、`bake_timeline.py` 注释、`mux.py` 顶部。

## TTS 接口备忘(踩坑点)

MiMo 的 TTS **不是** OpenAI 的 `/v1/audio/speech`(那个返回 404),而是复用
`/v1/chat/completions`:

```
POST {base}/v1/chat/completions
{
  "model": "mimo-v2.5-tts",
  "messages": [
    {"role": "user",      "content": "语气指令(自然语言)"},
    {"role": "assistant", "content": "待合成的正文"}
  ],
  "audio": {"format": "wav", "voice": "白桦", "optimize_text_preview": true}
}
```

音频在 `choices[0].message.audio.data`(base64 WAV,24kHz 单声道 16bit)。
`messages` 必须含 assistant 角色,否则报 `messages must contain an assistant role`。
