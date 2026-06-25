"""Chapter splitter for raw .txt corpus.

Steps
-----
1. Detect encoding with chardet (corpus is GBK in practice).
2. Decode to UTF-8, write a normalized copy under ``data/corpus/``.
3. Regex-locate chapter headings; record (number, title, char_offset) per chapter.
4. Insert into ``chapters`` table and the FTS5 virtual table for BM25 recall.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import chardet
from sqlalchemy import delete, text

from ..books.library import active_paths
from ..db import get_engine, session_scope
from ..memory.models import Chapter
from ..memory.schema_init import init_schema

CHAPTER_PATTERN = re.compile(
    # 允许标题前有缩进空白(半角空格/全角空格 U+3000/Tab)——如《九州·缥缈录》
    # 章节标题为「　　第一章 蛮荒〔一〕」,顶格锚定 ^第 会漏匹配(改进记录 #28)。
    r"^[ 　\t]*(?P<title>第(?P<num>[一二三四五六七八九十百千万零0-9]+)章[ 　\t]*[^\r\n]*)",
    re.MULTILINE,
)

CN_NUM = {ch: i for i, ch in enumerate("零一二三四五六七八九")}


def cn_to_int(s: str) -> int:
    """Convert Chinese numeral or arabic digits to int.

    Handles patterns up to 万. Sufficient for chapter indexing.
    """

    if s.isdigit():
        return int(s)
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    total = 0
    section = 0
    current = 0
    for ch in s:
        if ch in CN_NUM:
            current = CN_NUM[ch]
        elif ch in units:
            unit = units[ch]
            if unit == 10000:
                section = (section + (current or 1)) * unit
                total += section
                section = 0
            else:
                section += (current or 1) * unit
            current = 0
    return total + section + current


def detect_and_load(path: Path) -> str:
    raw = path.read_bytes()
    # Prefer Chinese encodings — chardet is unreliable on long Chinese text
    # (the novel here was misclassified as MacCyrillic without a UTF-8 BOM).
    candidates = ["utf-8-sig", "utf-8", "gb18030", "gbk", "big5"]
    if raw[:3] != b"\xef\xbb\xbf":
        candidates = ["gb18030", "gbk", "utf-8", "big5"]
    last_err: Exception | None = None
    for enc in candidates:
        try:
            decoded = raw.decode(enc)
            # sanity check: should contain at least one CJK character
            if any("一" <= c <= "鿿" for c in decoded[:1000]):
                return decoded
        except UnicodeDecodeError as e:
            last_err = e
            continue
    # fall back to chardet
    guess = chardet.detect(raw[:200_000]).get("encoding") or "gbk"
    try:
        return raw.decode(guess, errors="replace")
    except Exception as e:
        raise RuntimeError(f"could not decode {path}: {last_err or e}")


def split_chapters(text_body: str) -> list[tuple[int, str, int, int]]:
    """Return list of (sequence_number, title, char_offset_start, char_offset_end).

    The sequence number is **always continuous starting at 1** — multi-volume
    books like 龙族 restart "第一章" each volume, so the in-text chapter number
    cannot be the primary key. The original chapter heading is preserved in
    ``title``.
    """

    matches = list(CHAPTER_PATTERN.finditer(text_body))
    # First pass: compute body span for every match.
    raw: list[tuple[str, int, int]] = []
    for i, m in enumerate(matches):
        # 用 title 组起点(而非整个 match 起点)——前导缩进空白不计入正文偏移,
        # 下一章正文从其标题首字开始,切片干净。
        start = m.start("title")
        end = matches[i + 1].start("title") if i + 1 < len(matches) else len(text_body)
        raw.append((m.group("title").strip(), start, end))

    # Filter out TOC entries: a "real" chapter body is at least ~200 chars.
    # Multi-volume books like 龙族 have a table of contents that re-mentions
    # every chapter title, producing matches with body=10-50 chars each. We
    # treat anything under MIN_BODY_CHARS as TOC noise and drop it.
    MIN_BODY_CHARS = 200
    real = [r for r in raw if (r[2] - r[1]) >= MIN_BODY_CHARS]

    # Renumber sequentially. Keeps the original chapter heading in `title`,
    # but the PK `number` is the position in reading order.
    return [(i + 1, t, s, e) for i, (t, s, e) in enumerate(real)]


def ingest(path: Path) -> dict:
    init_schema()
    text_body = detect_and_load(path)
    # Persist a normalized utf-8 copy as the active book's canonical corpus.
    out_path = active_paths()["corpus_txt"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text_body, encoding="utf-8")

    chapters = split_chapters(text_body)
    if not chapters:
        raise RuntimeError("no chapters detected — pattern may need tuning")

    with session_scope() as s:
        s.execute(delete(Chapter))
        for num, title, start, end in chapters:
            s.add(Chapter(number=num, title=title, char_offset_start=start, char_offset_end=end))

    # Refresh FTS table.
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM chapter_fts"))
        for num, title, start, end in chapters:
            body = text_body[start:end]
            conn.execute(
                text("INSERT INTO chapter_fts(chapter, title, body) VALUES (:c, :t, :b)"),
                {"c": num, "t": title, "b": body},
            )

    return {
        "corpus_utf8": str(out_path),
        "chapters": len(chapters),
        "first_chapter": chapters[0][1],
        "last_chapter": chapters[-1][1],
        "total_chars": len(text_body),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    info = ingest(Path(args.path))
    for k, v in info.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
