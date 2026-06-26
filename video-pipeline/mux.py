#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
墨析 · 解析视频 —— 合成音轨 + 混流(第 4 步,多视频)
用法:python3 mux.py [video]
把各段旁白按各幕起始时刻 adelay+amix 成完整音轨,与 _build/<video>/silent.mp4 混流成 spec.out。
时刻公式(与 *-video.html 时间轴一致):
  AD[i]=LEAD+NARR[i]+TAIL ; S[0]=0,S[i]=S[i-1]+AD[i-1]-XF ; start[i]=S[i]+LEAD ; END=S[-1]+AD[-1]
"""
import os, sys, json, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SPECS = json.load(open(os.path.join(HERE, "specs.json"), encoding="utf-8"))
VIDEO = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("VIDEO", "architecture"))
SPEC = SPECS[VIDEO]
T = SPEC["timing"]
LEAD, TAIL, XF = T["LEAD"], T["TAIL"], T["XF"]
BUILD = os.path.join(HERE, "_build", VIDEO)
SILENT, VOICE = os.path.join(BUILD, "silent.mp4"), os.path.join(BUILD, "voice.wav")
OUT = os.path.normpath(os.path.join(HERE, SPEC["out"]))


def main():
    durs = json.load(open(os.path.join(BUILD, "durations.json"), encoding="utf-8"))["durs"]
    n = len(durs)
    AD = [LEAD + d + TAIL for d in durs]
    S = [0.0]
    for i in range(1, n):
        S.append(S[-1] + AD[i - 1] - XF)
    starts = [S[i] + LEAD for i in range(n)]
    END = S[-1] + AD[-1]
    print(f"[{VIDEO}] 起始(s):", [round(s, 2) for s in starts], "END=%.3f" % END)
    if not os.path.exists(SILENT):
        sys.exit(f"缺少 {SILENT};请先运行 render.mjs {VIDEO}。")
    inputs = []
    for i in range(n):
        inputs += ["-i", os.path.join(BUILD, f"seg{i}.wav")]
    fc = ";".join(f"[{i}]adelay={int(round(starts[i]*1000))}:all=1[a{i}]" for i in range(n))
    fc += ";" + "".join(f"[a{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,apad,atrim=0:{END:.3f}[mix]"
    r = subprocess.run(["ffmpeg", "-y"] + inputs + ["-filter_complex", fc, "-map", "[mix]", "-c:a", "pcm_s16le", VOICE],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit("音轨合成失败:\n" + r.stderr[-800:])
    r2 = subprocess.run(["ffmpeg", "-y", "-i", SILENT, "-i", VOICE, "-c:v", "copy", "-c:a", "aac",
                         "-b:a", "192k", "-ac", "1", "-movflags", "+faststart", "-shortest", OUT],
                        capture_output=True, text=True)
    if r2.returncode:
        sys.exit("混流失败:\n" + r2.stderr[-800:])
    print("成片 OK →", OUT)


if __name__ == "__main__":
    main()
