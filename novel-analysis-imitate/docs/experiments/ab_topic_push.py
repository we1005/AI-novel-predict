"""#78 话题 push 增强 · 命令行 A/B(复用 draft.pipeline.ab_topic_push)。

对同一章写两遍(push 关=基线 vs 开=增强)+ 盲评,打印两份初稿与裁决。
可对多章循环、统计胜率,结论沉淀进 docs/实验与操作台账.md。

前置:先 set_active 到目标书,且该书已有一个可用的 OutlineRun(写作页能选到)。
跑:backend/.venv/bin/python novel-analysis-imitate/docs/experiments/ab_topic_push.py \
        --slug 余烬之铳 --outline-run 12 --chapters 121 122 123
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", help="活动书 slug(不传则用当前 active)")
    ap.add_argument("--outline-run", type=int, required=True, help="OutlineRun id")
    ap.add_argument("--chapters", type=int, nargs="+", required=True, help="要对比的章号(可多个)")
    ap.add_argument("--no-judge", action="store_true", help="只出两稿,不盲评")
    args = ap.parse_args()

    from app.books import library
    from app.db import book_scope
    from app.draft import pipeline
    from contextlib import nullcontext

    slug = args.slug or library.get_active()
    wins = {"on": 0, "off": 0, "平/未知": 0}
    with (book_scope(slug) if slug else nullcontext()):
        for ch in args.chapters:
            print(f"\n{'='*70}\n第 {ch} 章 · A/B(push 关 vs 开)\n{'='*70}")
            r = pipeline.ab_topic_push(outline_run_id=args.outline_run,
                                       chapter_index=ch, judge=not args.no_judge)
            print(f"话题关键词: {r['must_include'][:5]}")
            print(f"[基线 off] 参考章 {r['off']['ref_chapters']} · ${r['off']['cost_usd']}")
            print(f"[增强 on ] 参考章 {r['on']['ref_chapters']} · push {len(r['on']['pushed_refs'])} 条 · ${r['on']['cost_usd']}")
            if r.get("judge"):
                w = r["judge"].get("winner_variant", "?")
                wins[w] = wins.get(w, 0) + 1
                print(f"盲评胜出: {w} · {r['judge'].get('reason','')}")
            print(f"\n--- 基线节选 ---\n{(r['off']['prose'] or '')[:500]}")
            print(f"\n--- 增强节选 ---\n{(r['on']['prose'] or '')[:500]}")

    if not args.no_judge:
        n = sum(wins.values())
        print(f"\n{'='*70}\n汇总({n} 章): push 开胜 {wins.get('on',0)} / 基线胜 {wins.get('off',0)} / 平 {wins.get('平/未知',0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
