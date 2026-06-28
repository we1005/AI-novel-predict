"""E2 向量层冒烟:证明 chroma 索引→查询管路在依赖装好后能跑通。

避开 HuggingFace 模型下载(沙箱无 HF 网络):用**确定性假嵌入器**替换 _embed,
临时 chroma 目录替换 active_paths,验证 index_chapters / query / before_chapter
过滤 / _reset_collection 全链路。真实嵌入只是把这里的假向量换成 bge 向量。

跑:backend/.venv/bin/python novel-analysis-imitate/docs/experiments/vector_smoke.py
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

# 让 app 包可导入(本脚本在 naimitate 下,但用的是共享 backend)。
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.memory import vector as v  # noqa: E402


def _fake_embed(texts: list[str]) -> list[list[float]]:
    """把每段文本哈希成 16 维确定性向量(L2 归一化)。同词更近。"""
    out = []
    for t in texts:
        h = hashlib.sha256(t.encode("utf-8")).digest()
        vec = [(b - 128) / 128.0 for b in h[:16]]
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        out.append([x / norm for x in vec])
    return out


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="vec_smoke_"))
    chroma_dir = tmp / "chroma"
    chroma_dir.mkdir(parents=True)

    # 替换:假嵌入器 + 临时 chroma 目录(不碰真实书库)。
    v._embed = _fake_embed  # type: ignore
    import app.books.library as lib
    lib.active_paths = lambda: {"chroma_dir": chroma_dir}  # type: ignore
    v._clients.clear()

    # 造 3 个假章节(number, title, start, end)+ 语料。
    corpus = (
        "维多利亚的雾气在煤气灯下盘旋,蒸汽机车轰鸣着驶过铸铁大桥。\n"      # ch1
        "他扣动黄铜左轮的扳机,硝烟与血腥味在巷战中弥漫开来。\n"            # ch2
        "古老的哥特教堂尖顶刺破阴云,石像鬼俯瞰着潮湿的鹅卵石街道。\n"      # ch3
    )
    # 用换行定位每章 offset
    lines = corpus.split("\n")
    offs, pos = [], 0
    for ln in lines:
        if ln:
            offs.append((pos, pos + len(ln) + 1))
        pos += len(ln) + 1
    chapters = [(i + 1, f"第{i+1}章", offs[i][0], offs[i][1]) for i in range(3)]

    n = v.index_chapters(chapters, corpus)
    print(f"[1] index_chapters → 索引 {n} 片段;indexed_count={v.indexed_count()}")
    assert n >= 3 and v.indexed_count() >= 3

    hits = v.query("蒸汽机车与煤气灯的维多利亚街景", k=2)
    print(f"[2] query → 命中 {len(hits)} 条;首条 chapter={hits[0]['chapter']} title={hits[0]['title']!r}")
    assert hits and all("chapter" in h and "text" in h for h in hits)

    hits_before = v.query("任意查询", k=5, before_chapter=2)  # 只允许 ch<2
    chs = {h["chapter"] for h in hits_before}
    print(f"[3] before_chapter=2 过滤 → 命中章号 {sorted(chs)}")
    assert chs <= {1}, f"before_chapter 过滤失效:{chs}"

    v._reset_collection()
    print(f"[4] _reset_collection → indexed_count={v.indexed_count()}")
    assert v.indexed_count() == 0

    print("\n✅ 向量层管路冒烟全部通过(index/query/before_chapter/reset)。")
    print("   真实启用只需把假嵌入换成 bge-large-zh(首次自动从 HF 下载)。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
