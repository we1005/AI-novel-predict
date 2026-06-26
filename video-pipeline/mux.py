#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
墨析 · 架构解析视频 —— 合成音轨 + 混流(第 4 步)

把 7 段旁白(_build/segN.wav)按各幕起始时刻拼成完整音轨,再与无声视频
(_build/silent.mp4)混流成最终 architecture.mp4。

每幕起始时刻按与 architecture-video.html 时间轴相同的公式推算:
    AD[i]   = LEAD + NARR[i] + TAIL              # 该幕在屏停留时长
    S[0]=0; S[i] = S[i-1] + AD[i-1] - XF         # 各幕开始时刻(幕间交叠 XF)
    start[i]= S[i] + LEAD                         # 该幕旁白入声时刻(留前导)
    END     = S[6] + AD[6]                        # 总时长
ffmpeg:每段 adelay 到 start[i] 毫秒后 amix(normalize=0 保电平),apad+atrim 补到 END。

⚠️ 下面四个常数必须与 architecture-video.html / bake_timeline.py 一致。
"""
import os, json, subprocess, sys

LEAD, TAIL, XF = 0.45, 0.95, 0.15   # 必须与 architecture-video.html 同步

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "_build")
SILENT = os.path.join(BUILD, "silent.mp4")
VOICE = os.path.join(BUILD, "voice.wav")
OUT = os.path.abspath(os.environ.get("VIDEO_OUT", os.path.join(HERE, "..", "novel-analysis-imitate", "docs", "architecture.mp4")))


def main():
    durs = json.load(open(os.path.join(BUILD, "durations.json"), encoding="utf-8"))["durs"]
    n = len(durs)
    AD = [LEAD + d + TAIL for d in durs]
    S = [0.0]
    for i in range(1, n):
        S.append(S[-1] + AD[i - 1] - XF)
    starts = [S[i] + LEAD for i in range(n)]
    END = S[-1] + AD[-1]
    print("起始时刻(s):", [round(s, 2) for s in starts], " END=%.3f" % END)

    if not os.path.exists(SILENT):
        sys.exit(f"缺少无声视频 {SILENT};请先运行 render.mjs。")

    # 1) 合成完整音轨
    inputs = []
    for i in range(n):
        inputs += ["-i", os.path.join(BUILD, f"seg{i}.wav")]
    fc = ";".join(f"[{i}]adelay={int(round(starts[i]*1000))}:all=1[a{i}]" for i in range(n))
    fc += ";" + "".join(f"[a{i}]" for i in range(n)) + \
          f"amix=inputs={n}:normalize=0,apad,atrim=0:{END:.3f}[mix]"
    r = subprocess.run(["ffmpeg", "-y"] + inputs +
                       ["-filter_complex", fc, "-map", "[mix]", "-c:a", "pcm_s16le", VOICE],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit("音轨合成失败:\n" + r.stderr[-800:])
    print("音轨 OK →", VOICE)

    # 2) 混流(视频流直拷,音频转 AAC)
    r2 = subprocess.run(["ffmpeg", "-y", "-i", SILENT, "-i", VOICE,
                         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ac", "1",
                         "-movflags", "+faststart", "-shortest", OUT],
                        capture_output=True, text=True)
    if r2.returncode:
        sys.exit("混流失败:\n" + r2.stderr[-800:])
    print("成片 OK →", OUT)


if __name__ == "__main__":
    main()
