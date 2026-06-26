#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
墨析 · 解析视频 —— 旁白合成(第 1 步,多视频)

用小米 MiMo TTS(mimo-v2.5-tts)把 specs.json 里某个视频的解说词合成为 WAV,落 durations.json。
- 用法:python3 narrate.py [video]      video 默认 architecture,另有 genome
- 接口:POST {base}/v1/chat/completions
    model = mimo-v2.5-tts
    messages = [{role:user, 语气指令}, {role:assistant, 待合成文本}]
    audio   = {format:"wav", voice:"白桦", optimize_text_preview:true}
  返回:choices[0].message.audio.data → base64 WAV(24kHz 单声道 16bit)
- API Key 只从 backend/data/settings.json(已 gitignore)读取,绝不写进脚本/产物。
- 仅用 Python 标准库 + ffprobe。
可用音色:mimo_default / 冰糖 / 茉莉 / 苏打 / 白桦(男) / Mia / Chloe / Milo / Dean
改旁白:编辑 specs.json 对应视频的 narr 数组(顺序对应各幕)。
"""
import os, sys, json, time, base64, subprocess, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
SETTINGS = os.environ.get("MOBI_SETTINGS", os.path.join(REPO, "backend", "data", "settings.json"))
SPECS = json.load(open(os.path.join(HERE, "specs.json"), encoding="utf-8"))
VIDEO = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("VIDEO", "architecture"))
if VIDEO not in SPECS:
    sys.exit(f"未知视频 {VIDEO!r};specs.json 里有:{[k for k in SPECS if not k.startswith('_')]}")
SPEC = SPECS[VIDEO]
NARR = SPEC["narr"]
VOICE = os.environ.get("TTS_VOICE", SPEC.get("voice", "白桦"))
OUT = os.path.join(HERE, "_build", VIDEO)
TONE = "用沉稳、专业的纪录片旁白语气朗读,语速适中偏慢,吐字清晰,情绪克制而有质感,书面语。"


def load_creds():
    cfg = json.load(open(SETTINGS, encoding="utf-8"))
    x = cfg["providers"]["xiaomi"]
    key, base = x.get("api_key") or "", (x.get("base_url") or "").rstrip("/")
    if not key or not base:
        sys.exit(f"未在 {SETTINGS} 找到 xiaomi 的 api_key/base_url")
    return key, base


def synth(text, idx, key, base, tries=4):
    body = {"model": "mimo-v2.5-tts",
            "messages": [{"role": "user", "content": TONE}, {"role": "assistant", "content": text}],
            "audio": {"format": "wav", "voice": VOICE, "optimize_text_preview": True}}
    H = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for k in range(tries):
        try:
            req = urllib.request.Request(base + "/chat/completions",
                                         data=json.dumps(body).encode(), headers=H, method="POST")
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read())
            return base64.b64decode(d["choices"][0]["message"]["audio"]["data"])
        except urllib.error.HTTPError as e:
            print(f"  seg{idx} HTTP {e.code} (try {k+1}): {e.read()[:200].decode('utf-8','replace')}")
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
    print(f"视频={VIDEO}  音色={VOICE}  段数={len(NARR)}")
    durs = []
    for i, t in enumerate(NARR):
        raw = synth(t, i, key, base)
        p = os.path.join(OUT, f"seg{i}.wav")
        open(p, "wb").write(raw)
        d = probe_dur(p)
        durs.append(d)
        print(f"seg{i}: {d:5.2f}s  {len(raw)//1024:>4}KB  «{t[:18]}…»")
        time.sleep(0.5)
    json.dump({"video": VIDEO, "voice": VOICE, "durs": durs, "narr": NARR},
              open(os.path.join(OUT, "durations.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"总旁白:{round(sum(durs), 2)}s  →  {OUT}/durations.json")


if __name__ == "__main__":
    main()
