#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""消融实验:写场景前"检索原著相似描写来参考",到底有没有用 / agentic 是否优于 push?

三组(保留双轨 + 可对比,对应 agentic-search 议题):
  A 无参考      —— 只给主题,直接写(基线)
  B push 预取   —— 编排器先用 search_corpus 取 top-k 原著片段,注入后写
  C agentic 自取 —— 先让 LLM 自己决定检索 query(JSON-in-text),再 search、注入后写

度量(无 LLM):用 naimitate._fingerprint 的结构维指纹,算每段产出对"原著参考指纹"的 fidelity
(越高=文风越贴近原著)。同主题多次采样取均值。可选:加一个更强模型盲评(默认开)。

用法:python3 ablation_search.py [book_slug]   默认 余烬之铳
key 从 backend/data/settings.json(gitignore)读;生成与盲评用小米 MiMo。
"""
import os
import sys
import json
import re
import time
import urllib.request
import urllib.error
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "novel-analysis-imitate", "backend"))

from app.db import book_scope, get_engine          # noqa: E402
from app.craft import search as craft_search        # noqa: E402
from naimitate.analysis import _fingerprint as FP    # noqa: E402
from sqlalchemy import text as _sql                  # noqa: E402

BOOK = sys.argv[1] if len(sys.argv) > 1 else "余烬之铳"
GEN_MODEL = "mimo-v2.5"
JUDGE_MODEL = "mimo-v2.5-pro"
SAMPLES = 2
THEMES = [
    "维多利亚风格的古老建筑与街道景物",
    "雨夜的码头,海雾弥漫,远处有船",
    "教堂内部,钟声、烛火与压抑的祈祷",
    "一场近身搏杀,刀光与血",
]

_cfg = json.load(open(os.path.join(ROOT, "backend", "data", "settings.json"), encoding="utf-8"))
_x = _cfg["providers"]["xiaomi"]
_KEY, _BASE = _x["api_key"], _x["base_url"].rstrip("/")
_H = {"Authorization": f"Bearer {_KEY}", "Content-Type": "application/json"}


def chat(model, system, user, max_tokens=1200, temp=0.9, tries=4):
    body = {"model": model, "messages": [{"role": "system", "content": system},
                                         {"role": "user", "content": user}],
            "max_completion_tokens": max_tokens, "temperature": temp, "top_p": 0.95}
    for k in range(tries):
        try:
            req = urllib.request.Request(_BASE + "/chat/completions", data=json.dumps(body).encode(),
                                         headers=_H, method="POST")
            return json.loads(urllib.request.urlopen(req, timeout=180).read())["choices"][0]["message"]["content"] or ""
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(3 * (k + 1)); continue
            time.sleep(2)
        except Exception:
            time.sleep(2)
    return ""


def _refs_block(hits):
    return "\n\n".join(f"【参考{i+1}·第{h['chapter']}章】{h['snip']}" for i, h in enumerate(hits))


SYS_PLAIN = "你是中文小说写手。只写正文,约600字,不要标题/解释。"
SYS_REF = ("你是中文小说写手。下面给出同一部作品的若干原文片段,请揣摩其用词、句式、节奏与氛围,"
           "写一段约600字的新场景,文风尽量贴近这些片段。只写正文,不要标题/解释。")


def arm_plain(theme):
    return chat(GEN_MODEL, SYS_PLAIN, f"写一段场景:{theme}。")


def arm_push(theme):
    hits = craft_search.search_corpus(theme, k=3)
    if not hits:
        return chat(GEN_MODEL, SYS_PLAIN, f"写一段场景:{theme}。"), 0
    user = f"要写的场景:{theme}。\n\n{_refs_block(hits)}"
    return chat(GEN_MODEL, SYS_REF, user), len(hits)


def arm_agentic(theme):
    # step1:让 LLM 自己决定检索什么(JSON-in-text)
    q = chat(GEN_MODEL, "你是检索策略助手。只输出 JSON。",
             f"我要写这样一个小说场景:{theme}。\n为了参考原著里相似的已有描写,你会用哪 2-3 个检索短语"
             f"(每个≥6字的自然短语,便于全文检索)?只输出 JSON:{{\"queries\":[\"...\"]}}",
             max_tokens=400, temp=0.4)
    try:
        from json_repair import repair_json
        queries = json.loads(repair_json(re.sub(r"```json|```", "", q)))["queries"][:3]
    except Exception:
        queries = [theme]
    hits, seen = [], set()
    for qq in queries:
        for h in craft_search.search_corpus(str(qq), k=2):
            if h["chapter"] not in seen:
                seen.add(h["chapter"]); hits.append(h)
    if not hits:
        return chat(GEN_MODEL, SYS_PLAIN, f"写一段场景:{theme}。"), queries, 0
    user = f"要写的场景:{theme}。\n\n{_refs_block(hits[:4])}"
    return chat(GEN_MODEL, SYS_REF, user), queries, len(hits)


def source_ref_fp():
    with get_engine().begin() as c:
        rows = c.execute(_sql("SELECT body FROM chapter_fts ORDER BY chapter LIMIT 12")).all()
    return FP.fingerprint_from_text("\n".join(r[0] for r in rows if r[0]))


def judge(ref_excerpt, passage):
    s = chat(JUDGE_MODEL, "你是严格文风评审,只输出一个 0-100 整数。",
             f"参考(原著真实片段):\n{ref_excerpt}\n\n候选:\n{passage}\n\n"
             f"候选在文风(用词/句式/氛围)上与参考有多接近、且作为场景写得好不好?给 0-100,只输出数字。",
             max_tokens=1500, temp=0.3)
    m = re.search(r"\d+", s or "")
    return int(m.group()) if m else None


def main():
    with book_scope(BOOK):
        src = source_ref_fp()
        with get_engine().begin() as c:
            ref_excerpt = (c.execute(_sql("SELECT body FROM chapter_fts ORDER BY chapter LIMIT 1")).scalar() or "")[:600]

        def fid(passage):
            return FP.compare(src, FP.fingerprint_from_text(passage)).get("fidelity_score")

        results = {a: {"fid": [], "judge": []} for a in ("A_无参考", "B_push", "C_agentic")}
        for theme in THEMES:
            print(f"\n=== 主题:{theme} ===")
            for _ in range(SAMPLES):
                pa = arm_plain(theme)
                pb, nb = arm_push(theme)
                pc, qs, nc = arm_agentic(theme)
                for name, p in (("A_无参考", pa), ("B_push", pb), ("C_agentic", pc)):
                    if not p:
                        continue
                    f = fid(p); j = judge(ref_excerpt, p)
                    if f is not None:
                        results[name]["fid"].append(f)
                    if j is not None:
                        results[name]["judge"].append(j)
                print(f"  push命中={nb} agentic查询={qs} agentic命中={nc}")
                time.sleep(0.3)

        print("\n" + "=" * 56)
        print(f"{'组别':<12}{'fidelity均值':>14}{'盲评均值':>12}{'样本':>8}")
        out = {}
        for a, d in results.items():
            fa = round(st.mean(d["fid"]), 1) if d["fid"] else None
            ja = round(st.mean(d["judge"]), 1) if d["judge"] else None
            out[a] = {"fidelity": fa, "judge": ja, "n": len(d["fid"])}
            print(f"{a:<12}{str(fa):>14}{str(ja):>12}{len(d['fid']):>8}")
        json.dump({"book": BOOK, "themes": THEMES, "samples": SAMPLES, "result": out},
                  open(os.path.join(HERE, "ablation_search_results.json"), "w"), ensure_ascii=False, indent=2)
        print("\n结果落 ablation_search_results.json")
        print("判读:B/C 明显高于 A → 检索参考有用;C 不显著高于 B 却更慢 → agentic 是过度设计,只留 push。")


if __name__ == "__main__":
    main()
