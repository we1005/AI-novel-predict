#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
墨析 · 架构解析视频 —— 旁白合成(第 1 步)

用小米 MiMo TTS(mimo-v2.5-tts)把 7 段解说词合成为 WAV,并落 durations.json。
- 接口:POST {base}/v1/chat/completions
    body.model = mimo-v2.5-tts
    body.messages = [{role:user, content:语气指令}, {role:assistant, content:待合成文本}]
    body.audio  = {format:"wav", voice:"白桦", optimize_text_preview:true}
  返回:choices[0].message.audio.data  → base64 WAV(24kHz 单声道 16bit)
- API Key 只从 backend/data/settings.json(已 gitignore)读取,绝不写进脚本/产物。
- 仅用 Python 标准库 + ffprobe,无需第三方包。

可用音色:mimo_default / 冰糖(女) / 茉莉(女) / 苏打(男) / 白桦(男) / Mia / Chloe / Milo / Dean
改旁白:直接编辑下方 NARR(每幕一段,顺序对应 序→墨滴→切分→分析簇→基因组→compose→评测)。
"""
import os, sys, json, time, base64, subprocess, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SETTINGS = os.environ.get("MOBI_SETTINGS", os.path.join(REPO, "backend", "data", "settings.json"))
OUT = os.path.join(HERE, "_build")

VOICE = os.environ.get("TTS_VOICE", "白桦")
TONE  = "用沉稳、专业的纪录片旁白语气朗读,语速适中偏慢,吐字清晰,情绪克制而有质感,书面语。"

# 7 幕解说词 —— 与 architecture-video.html 的 序+6 幕一一对应
NARR = [
    # 序
    "墨析,一套中文小说的深度分析与仿写引擎。它想回答一个问题:一个作者的文风,能不能被拆解、被存下、再被复现?",
    # 幕1 墨滴
    "一切的起点,是一整本尚未被理解的原著。百万字,此刻只是一滴沉入水中的墨,一团混沌的整体。",
    # 幕2 切分
    "第一步,是把这团混沌嚼碎。整本被切成时序章节,建立全文检索索引与召回机制;原著由此才能被逐段调取,交给多个智能体拆解。",
    # 幕3 分析簇
    "接着,十三个视角同时展开。六项基础抽取,梳理实体、伏笔、状态、剧情点、世界规则与谜团;另有八个分析层,从速读、节拍张力,到人物关系与视角调度。逐章逐事件,沉淀进这本书自己的库。",
    # 幕4 基因组
    "其中最核心的,是文风基因组。我们把笼统的文风,分光成七层可计算的指纹:从词汇分层、句式构式,到修辞声音、宏观架构与转移模型。每一层都可被路由、带有逐字锚点,连用词密度都能精确到每千字零点四二。",
    # 幕5 compose
    "复现的时候,这些声音、笔法与基因组规格,被装进一本虚拟书;再交给生成内核,经过三道审校与一次统编,写出风格一致的新作。",
    # 幕6 评测
    "最后,是评测闭环。用同一把抽取出的尺子,反过来丈量产出。七维盲评加上指纹对账,分层基因组以六十五点二五分,全面领先单段总结的五十六点七五分。至此,文风,被看见,也被复现。",
]


def load_creds():
    cfg = json.load(open(SETTINGS, encoding="utf-8"))
    x = cfg["providers"]["xiaomi"]
    key = x.get("api_key") or ""
    base = (x.get("base_url") or "").rstrip("/")
    if not key or not base:
        sys.exit(f"未在 {SETTINGS} 找到 xiaomi 的 api_key/base_url")
    return key, base


def synth(text, idx, key, base, tries=4):
    body = {
        "model": "mimo-v2.5-tts",
        "messages": [{"role": "user", "content": TONE},
                     {"role": "assistant", "content": text}],
        "audio": {"format": "wav", "voice": VOICE, "optimize_text_preview": True},
    }
    H = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for k in range(tries):
        try:
            req = urllib.request.Request(base + "/chat/completions",
                                         data=json.dumps(body).encode(), headers=H, method="POST")
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read())
            return base64.b64decode(d["choices"][0]["message"]["audio"]["data"])
        except urllib.error.HTTPError as e:
            msg = e.read()[:200].decode("utf-8", "replace")
            print(f"  seg{idx} HTTP {e.code} (try {k+1}): {msg}")
            if e.code == 429:
                time.sleep(3 * (k + 1)); continue
            if k == tries - 1:
                raise
            time.sleep(2)
        except Exception as e:
            print(f"  seg{idx} err (try {k+1}): {e}")
            if k == tries - 1:
                raise
            time.sleep(2)


def probe_dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nk=1:nw=1", path], capture_output=True, text=True).stdout.strip()
    return round(float(out), 3)


def main():
    os.makedirs(OUT, exist_ok=True)
    key, base = load_creds()
    durs = []
    for i, t in enumerate(NARR):
        raw = synth(t, i, key, base)
        p = os.path.join(OUT, f"seg{i}.wav")
        open(p, "wb").write(raw)
        d = probe_dur(p)
        durs.append(d)
        print(f"seg{i}: {d:5.2f}s  {len(raw)//1024:>4}KB  «{t[:18]}…»")
        time.sleep(0.5)
    json.dump({"voice": VOICE, "durs": durs, "narr": NARR},
              open(os.path.join(OUT, "durations.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"总旁白:{round(sum(durs), 2)}s  →  {OUT}/durations.json")


if __name__ == "__main__":
    main()
