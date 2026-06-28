#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重合度校验:push 的高盲评分,是"真学到文风"还是"照抄注入的参考片段"?(参考变抄/自我抄袭)

对每个主题:
  - 取与消融同款的注入参考(search_corpus 的 snip,与 ablation_search.py 一致)
  - 生成 push 产出(看参考)与 plain 产出(没看参考,作偶然重合基线)
  - 算产出 vs 参考文本的:① 最长公共子串(LCS,连续逐字抄的长度);② ≥8字逐字片段覆盖率(被抄占比)
若 push 的 LCS/覆盖率 远高于 plain → 高分含照抄水分;若与 plain 接近 → 是真风格迁移而非抄。

样本产出会存进 ablation_overlap_samples.json(中间产物入库,便于复核)。
用法:python3 ablation_overlap.py [book_slug]   默认 余烬之铳
"""
import os
import sys
import json
import re
import time
import urllib.request
import urllib.error
import statistics as st
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.db import book_scope            # noqa: E402
from app.craft import search as cs        # noqa: E402

BOOK = sys.argv[1] if len(sys.argv) > 1 else "余烬之铳"
GEN_MODEL = "mimo-v2.5"
SAMPLES = 2
THEMES = [
    "维多利亚风格的古老建筑与街道景物",
    "雨夜的码头,海雾弥漫,远处有船",
    "教堂内部,钟声、烛火与压抑的祈祷",
    "一场近身搏杀,刀光与血",
]
_cfg = json.load(open(os.path.join(ROOT, "backend", "data", "settings.json"), encoding="utf-8"))
_x = _cfg["providers"]["xiaomi"]
_H = {"Authorization": f"Bearer {_x['api_key']}", "Content-Type": "application/json"}
_BASE = _x["base_url"].rstrip("/")
SYS_PLAIN = "你是中文小说写手。只写正文,约600字,不要标题/解释。"
SYS_REF = ("你是中文小说写手。下面给出同一部作品的若干原文片段,请揣摩其用词、句式、节奏与氛围,"
           "写一段约600字的新场景,文风尽量贴近这些片段。只写正文,不要标题/解释。")


def chat(system, user, tries=4):
    body = {"model": GEN_MODEL, "messages": [{"role": "system", "content": system},
            {"role": "user", "content": user}], "max_completion_tokens": 1200, "temperature": 0.9, "top_p": 0.95}
    for k in range(tries):
        try:
            req = urllib.request.Request(_BASE + "/chat/completions", data=json.dumps(body).encode(), headers=_H, method="POST")
            return json.loads(urllib.request.urlopen(req, timeout=180).read())["choices"][0]["message"]["content"] or ""
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(3 * (k + 1)); continue
            time.sleep(2)
        except Exception:
            time.sleep(2)
    return ""


def overlap(gen: str, ref: str, min_span: int = 8) -> dict:
    """gen 与 ref 的逐字重合:最长公共子串 + 被 ≥min_span 连续片段覆盖的字数占比。"""
    g = re.sub(r"\s", "", gen or "")
    r = re.sub(r"\s", "", ref or "")
    if not g or not r:
        return {"lcs": 0, "cover": 0.0}
    sm = SequenceMatcher(None, g, r, autojunk=False)
    blocks = sm.get_matching_blocks()
    lcs = max((b.size for b in blocks), default=0)
    covered = sum(b.size for b in blocks if b.size >= min_span)
    return {"lcs": lcs, "cover": round(covered / len(g), 3)}


def main():
    with book_scope(BOOK):
        push_lcs, push_cov, plain_lcs, plain_cov = [], [], [], []
        samples = []
        for theme in THEMES:
            hits = cs.search_corpus(theme, k=3)
            ref = "\n".join(h["snip"] for h in hits)
            print(f"\n=== {theme}  (参考 {len(hits)} 片段, 共 {len(ref)} 字) ===")
            for i in range(SAMPLES):
                gp = chat(SYS_REF, f"要写的场景:{theme}。\n\n参考片段:\n{ref}")
                ga = chat(SYS_PLAIN, f"写一段场景:{theme}。")
                op = overlap(gp, ref)
                oa = overlap(ga, ref)   # 对照:没看过参考,重合=偶然
                push_lcs.append(op["lcs"]); push_cov.append(op["cover"])
                plain_lcs.append(oa["lcs"]); plain_cov.append(oa["cover"])
                print(f"  s{i}: push LCS={op['lcs']:>2} 覆盖={op['cover']:.0%} | plain(对照) LCS={oa['lcs']:>2} 覆盖={oa['cover']:.0%}")
                if i == 0:
                    samples.append({"theme": theme, "ref": ref, "push": gp[:800], "plain": ga[:800],
                                    "push_overlap": op, "plain_overlap": oa})
                time.sleep(0.3)
        print("\n" + "=" * 56)
        print(f"push  平均 LCS={round(st.mean(push_lcs),1)} 字, 平均覆盖={round(st.mean(push_cov)*100,1)}%")
        print(f"plain 平均 LCS={round(st.mean(plain_lcs),1)} 字, 平均覆盖={round(st.mean(plain_cov)*100,1)}%(偶然基线)")
        verdict = ("push 重合≈plain → 高分是真风格迁移,非照抄"
                   if st.mean(push_cov) <= st.mean(plain_cov) + 0.05 and st.mean(push_lcs) <= st.mean(plain_lcs) + 6
                   else "push 重合明显高于 plain → 高分含照抄水分(参考变抄)")
        print("判读:", verdict)
        json.dump({"book": BOOK,
                   "push": {"lcs_avg": round(st.mean(push_lcs), 1), "cover_avg": round(st.mean(push_cov), 3)},
                   "plain": {"lcs_avg": round(st.mean(plain_lcs), 1), "cover_avg": round(st.mean(plain_cov), 3)},
                   "verdict": verdict, "samples": samples},
                  open(os.path.join(HERE, "ablation_overlap_results.json"), "w"), ensure_ascii=False, indent=2)
        print("结果+样本落 ablation_overlap_results.json")


if __name__ == "__main__":
    main()
