# -*- coding: utf-8 -*-
"""《姝爻误》专用切分脚本(通用切分器切不了它)。

为什么单独写:这本书不是章回体,没有「第N章」标题——它用
  · 序章:`序章 背叛 两相依`
  · 正文:`01 山村人空烟未冷` … `55 数年不现君颜变`(两位数编号 + 七字标题,有的有空格有的没有)
每章正文之后跟一段 `………以下已非正文………` 分隔的附录(人物表/作者的话/寄首词/txtsk 广告),
本脚本把这段附录从正文里剔除,只把纯故事正文写进 chapters + chapter_fts。

产物与通用 split.ingest() 完全同构:
  · chapters(number 连续 1..N、title 保留原标题、char_offset_start/end 指向 corpus_txt 里的纯正文跨度)
  · chapter_fts(chapter/title/body,body=纯正文,不含附录)
下游 extract/draft/FTS 都按 number 取用,故 number 用「阅读顺序位置」而非书里的 01/02。

跑:  backend/.venv/bin/python -m scripts.split_shuyaowu            # 默认写库
     backend/.venv/bin/python -m scripts.split_shuyaowu --dry-run  # 只预览不写
"""
from __future__ import annotations

import argparse
import re
import sys

from sqlalchemy import delete, text

from app.books import library
from app.db import book_scope, get_engine, session_scope
from app.memory.models import Chapter
from app.memory.schema_init import init_schema

SLUG = "姝爻误全集"

# 标题行:序章(可带副标题) 或 「编号 + 4-12 个汉字」独占一行(允许编号后有空格/全角空格)。
# 结尾锚 $ + 纯汉字标题,天然排除:人物表条目(`姓名:描述`,含冒号且长)、正文段落(含标点/超长)。
HEADING_RE = re.compile(
    r"^[ \t　]*("
    r"序章[ \t　].*|序章|"
    # 编号 + 4-10 汉字标题 +(可选括号后缀,如「（天佑中华）」)+(可选尾部点号,如「40 相逢一笑空余梦.」)
    r"\d{1,3}[ \t　]*[一-鿿]{4,10}(?:[（(][^）)\n]{0,12}[）)])?[.．。]*"
    r")[ \t　]*$",
    re.M,
)

# 正文终止标记:作者自标的「以下已非正文」,或书末的暂停语/txtsk 广告/版权声明。
# 命中后正文截到该标记所在行的行首(把前导 ……… 一并排除)。
TERMINATORS = ("以下已非正文", "本书就要暂停", "更多免费txt", "声明：本电子书", "手机装有主流阅览器")

MIN_BODY_CHARS = 200  # 与通用切分器一致:太短的疑似目录/噪声,丢弃


def _body_end_in(segment: str, seg_start: int) -> int:
    """在 [章标题 .. 下一章标题) 这段里,找最早的正文终止标记,返回其行首的全局 char 偏移;
    没有则返回整段末尾。"""
    best = None
    for term in TERMINATORS:
        idx = segment.find(term)
        if idx >= 0 and (best is None or idx < best):
            best = idx
    if best is None:
        return seg_start + len(segment)
    line_start = segment.rfind("\n", 0, best)  # 回退到该标记所在行的行首
    cut = line_start + 1 if line_start >= 0 else best
    return seg_start + cut


def split_shuyaowu(text_body: str) -> list[tuple[int, str, int, int]]:
    matches = list(HEADING_RE.finditer(text_body))
    raw: list[tuple[str, int, int]] = []
    for i, m in enumerate(matches):
        start = m.start(1)
        seg_end = matches[i + 1].start(1) if i + 1 < len(matches) else len(text_body)
        title = re.sub(r"\s+", " ", m.group(1).strip())
        body_end = _body_end_in(text_body[start:seg_end], start)
        raw.append((title, start, body_end))
    real = [r for r in raw if (r[2] - r[1]) >= MIN_BODY_CHARS]
    return [(i + 1, t, s, e) for i, (t, s, e) in enumerate(real)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default=SLUG)
    ap.add_argument("--dry-run", action="store_true", help="只预览检测结果,不写库")
    args = ap.parse_args()

    with book_scope(args.slug):
        corpus = library.active_paths()["corpus_txt"]
        if not corpus.exists():
            print(f"✗ 找不到语料:{corpus}", file=sys.stderr)
            return 2
        text_body = corpus.read_text(encoding="utf-8")
        chapters = split_shuyaowu(text_body)

        print(f"书:{args.slug}  语料 {len(text_body)} 字符 → 检测到 {len(chapters)} 章")
        print("--- 抽检(前3 + 后2)---")
        for num, title, s, e in chapters[:3] + chapters[-2:]:
            head = text_body[s:e].strip().replace("\n", " ")[:36]
            print(f"  #{num:<3} {title:<16} 正文 {e - s:>6} 字 | 开头: {head}…")

        if args.dry_run:
            print("\n[dry-run] 未写库。去掉 --dry-run 即写入 chapters + chapter_fts。")
            return 0

        init_schema()
        with session_scope() as sess:
            sess.execute(delete(Chapter))
            for num, title, s, e in chapters:
                sess.add(Chapter(number=num, title=title, char_offset_start=s, char_offset_end=e))
        with get_engine().begin() as conn:
            conn.execute(text("DELETE FROM chapter_fts"))
            for num, title, s, e in chapters:
                conn.execute(
                    text("INSERT INTO chapter_fts(chapter, title, body) VALUES (:c, :t, :b)"),
                    {"c": num, "t": title, "b": text_body[s:e]},
                )
        print(f"\n✓ 已写入:{len(chapters)} 章 → chapters 表 + chapter_fts(纯正文,已剔除附录)。")
        print(f"  首章:{chapters[0][1]}  末章:{chapters[-1][1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
