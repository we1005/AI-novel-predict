#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
墨析 · 架构解析视频 —— 把旁白时长烘焙进时间轴(第 2 步)

读 _build/durations.json,替换 architecture-video.html 里的
    const NARR=[...];
这一行。HTML 内部用 NARR[] + (LEAD/TAIL/XF/X) 自行推算各幕起止时刻
(见该文件 master timeline 注释),所以这里只需要更新 NARR 数组。

⚠️ 时间轴常数必须与 mux.py / architecture-video.html 保持一致:
    LEAD=0.45  TAIL=0.95  XF=0.15  X(淡出)=0.45
"""
import os, re, json

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "..", "architecture-video.html")
DUR = os.path.join(HERE, "_build", "durations.json")


def main():
    durs = json.load(open(DUR, encoding="utf-8"))["durs"]
    html = open(HTML, encoding="utf-8").read()
    new_line = "const NARR=" + json.dumps(durs) + ";"
    html2, n = re.subn(r"const NARR=\[[^\]]*\];", new_line, html, count=1)
    if n != 1:
        raise SystemExit("未找到可替换的 `const NARR=[...]`;请确认 architecture-video.html 时间轴块存在。")
    open(HTML, "w", encoding="utf-8").write(html2)
    print(f"已写入 NARR={durs} → {os.path.relpath(HTML, HERE)}")


if __name__ == "__main__":
    main()
