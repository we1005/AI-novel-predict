#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
墨析 · 解析视频 —— 把旁白时长烘焙进时间轴(第 2 步,多视频)
用法:python3 bake_timeline.py [video]
读 _build/<video>/durations.json,替换该视频 HTML 里的 `const NARR=[...]` 一行。
HTML 内部用 NARR[] + (LEAD/TAIL/XF/X) 自行推算各幕起止。
⚠️ 时间轴常数须与 specs.json 的 timing、对应 *-video.html 一致。
"""
import os, re, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
SPECS = json.load(open(os.path.join(HERE, "specs.json"), encoding="utf-8"))
VIDEO = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("VIDEO", "architecture"))
SPEC = SPECS[VIDEO]
HTML = os.path.normpath(os.path.join(HERE, SPEC["html"]))
DUR = os.path.join(HERE, "_build", VIDEO, "durations.json")


def main():
    durs = json.load(open(DUR, encoding="utf-8"))["durs"]
    html = open(HTML, encoding="utf-8").read()
    new_line = "const NARR=" + json.dumps(durs) + ";"
    html2, n = re.subn(r"const NARR=\[[^\]]*\];", new_line, html, count=1)
    if n != 1:
        raise SystemExit(f"未找到可替换的 `const NARR=[...]`(video={VIDEO})")
    open(HTML, "w", encoding="utf-8").write(html2)
    print(f"[{VIDEO}] NARR={durs} → {os.path.relpath(HTML, HERE)}")


if __name__ == "__main__":
    main()
