#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agentic 公平复赛 v2:素材换成"整段原著片段(craft 标签库)",agentic 给更强的多路检索。

相比 v1 的两处改进(回应"给 agentic 公平机会" + craft 库已填):
  1. 注入素材 = craft_snippet 的整段 excerpt(~500字 真原文),而非 v1 的短 FTS 窗口(~40字)。
  2. C agentic 自己决定**检索哪些类目(scene_env/scene_place/combat…)+ 正文关键词**(多路),
     而非 v1 那样把主题原样当一句查询。这正是用户设想的"按景物/建筑标签检索"。

三组:A 无参考 / B push(场景→类目 启发式映射,注入该类 top-k 片段)/ C agentic(LLM 自选类目+查询)。
度量:结构维 fidelity + 盲评 + **逐字重合度**(整段注入→抄袭风险真实,必须查)。
用法:python3 ablation_search_v2.py [book_slug]   默认 余烬之铳
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
sys.path.insert(0, os.path.join(ROOT, "novel-analysis-imitate", "backend"))

from app.db import book_scope, get_engine      # noqa: E402
from app.craft import search as cs              # noqa: E402
from naimitate.analysis import _fingerprint as FP  # noqa: E402
from sqlalchemy import text as _sql              # noqa: E402

BOOK = sys.argv[1] if len(sys.argv) > 1 else "余烬之铳"
GEN, JUDGE, SAMPLES = "mimo-v2.5", "mimo-v2.5-pro", 2
CATS = ["scene_env", "scene_place", "object", "sensory", "appearance", "combat",
        "dialogue_subtext", "interior", "emotion_peak", "lyrical", "worldbuild", "ritual"]
THEMES = {
    "维多利亚风格的古老建筑与街道景物": ["scene_place", "scene_env"],
    "雨夜的码头,海雾弥漫,远处有船": ["scene_env", "sensory"],
    "教堂内部,钟声、烛火与压抑的祈祷": ["scene_place", "sensory"],
    "一场近身搏杀,刀光与血": ["combat"],
}
_x = json.load(open(os.path.join(ROOT, "backend", "data", "settings.json")))["providers"]["xiaomi"]
_H = {"Authorization": f"Bearer {_x['api_key']}", "Content-Type": "application/json"}
_BASE = _x["base_url"].rstrip("/")
SYS_PLAIN = "你是中文小说写手。只写正文,约600字,不要标题/解释。"
SYS_REF = ("你是中文小说写手。下面是同一部作品的若干原文片段,揣摩其用词/句式/节奏/氛围,"
           "写一段约600字的新场景,文风贴近这些片段,但**不要照抄原句**。只写正文。")


def chat(system, user, model=GEN, mt=1200, temp=0.9, tries=4):
    body = {"model": model, "messages": [{"role": "system", "content": system},
            {"role": "user", "content": user}], "max_completion_tokens": mt, "temperature": temp, "top_p": 0.95}
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


def _block(snips):
    return "\n\n".join(f"【参考{i+1}·第{s['chapter']}章】{s['excerpt']}" for i, s in enumerate(snips))


def arm_push(theme, cats):
    snips = []
    for c in cats:
        snips += cs.search_snippets(category=c, k=2, min_rep=70)
    snips = snips[:4]
    if not snips:
        return chat(SYS_PLAIN, f"写一段场景:{theme}。"), []
    return chat(SYS_REF, f"要写的场景:{theme}。\n\n{_block(snips)}"), snips


def arm_agentic(theme):
    plan = chat("你是检索策略助手。只输出 JSON。",
                f"我要写小说场景:{theme}。素材库按类目存了原著片段,类目有:{', '.join(CATS)}。"
                f"为最贴切地参考,你会查哪些类目(可多选,2-3个)、再补什么正文关键词(≥6字短语,1-2个)?"
                f'只输出 JSON:{{"categories":[...],"queries":[...]}}', mt=1500, temp=0.4)
    # 注:mt 从 400→1500——400 会截断 mimo 输出导致 JSON 解析失败、退化成默认值(对 agentic 不公平,已修)
    try:
        from json_repair import repair_json
        d = json.loads(repair_json(re.sub(r"```json|```", "", plan)))
        cats = [c for c in d.get("categories", []) if c in CATS][:3] or ["scene_env"]
        queries = [str(q) for q in d.get("queries", [])][:2]
    except Exception:
        cats, queries = ["scene_env"], [theme]
    snips, seen = [], set()
    for c in cats:
        for s in cs.search_snippets(category=c, k=2, min_rep=70):
            key = (s["chapter"], s["category"])
            if key not in seen:
                seen.add(key); snips.append(s)
    for q in queries:
        for h in cs.search_corpus(q, k=1):
            snips.append({"chapter": h["chapter"], "excerpt": h["snip"]})
    if not snips:
        return chat(SYS_PLAIN, f"写一段场景:{theme}。"), {"cats": cats, "queries": queries}, []
    return chat(SYS_REF, f"要写的场景:{theme}。\n\n{_block(snips[:5])}"), {"cats": cats, "queries": queries}, snips[:5]


def overlap(gen, ref, span=8):
    g, r = re.sub(r"\s", "", gen or ""), re.sub(r"\s", "", ref or "")
    if not g or not r:
        return {"lcs": 0, "cover": 0.0}
    bl = SequenceMatcher(None, g, r, autojunk=False).get_matching_blocks()
    return {"lcs": max((b.size for b in bl), default=0),
            "cover": round(sum(b.size for b in bl if b.size >= span) / len(g), 3)}


def main():
    with book_scope(BOOK):
        with get_engine().begin() as c:
            rows = c.execute(_sql("SELECT body FROM chapter_fts ORDER BY chapter LIMIT 12")).all()
            ref_excerpt = (c.execute(_sql("SELECT body FROM chapter_fts ORDER BY chapter LIMIT 1")).scalar() or "")[:600]
        src = FP.fingerprint_from_text("\n".join(r[0] for r in rows if r[0]))

        def fid(p):
            return FP.compare(src, FP.fingerprint_from_text(p)).get("fidelity_score")

        def judge(p):
            s = chat("你是严格文风评审,只输出 0-100 整数。",
                     f"参考(原著片段):\n{ref_excerpt}\n\n候选:\n{p}\n\n候选在文风(用词/句式/氛围)上与参考多接近、"
                     f"且作为场景写得好不好?给 0-100,只输出数字。", model=JUDGE, mt=1500, temp=0.3)
            m = re.search(r"\d+", s or "")
            return int(m.group()) if m else None

        R = {a: {"fid": [], "judge": [], "ov_lcs": [], "ov_cov": []} for a in ("A_无参考", "B_push", "C_agentic")}
        samples = []
        for theme, cats in THEMES.items():
            print(f"\n=== {theme} (push类目={cats}) ===")
            for i in range(SAMPLES):
                pa = chat(SYS_PLAIN, f"写一段场景:{theme}。")
                pb, sb = arm_push(theme, cats)
                pc, plan, sc = arm_agentic(theme)
                refb = "\n".join(s["excerpt"] for s in sb)
                refc = "\n".join(s["excerpt"] for s in sc)
                for name, p, ref in (("A_无参考", pa, refb), ("B_push", pb, refb), ("C_agentic", pc, refc)):
                    if not p:
                        continue
                    R[name]["fid"].append(fid(p)); R[name]["judge"].append(judge(p))
                    ov = overlap(p, ref or refb)
                    R[name]["ov_lcs"].append(ov["lcs"]); R[name]["ov_cov"].append(ov["cover"])
                print(f"  s{i}: agentic自选={plan}")
                if i == 0:
                    samples.append({"theme": theme, "agentic_plan": plan,
                                    "A": pa[:600], "B": pb[:600], "C": pc[:600]})
                time.sleep(0.3)

        def avg(xs):
            xs = [x for x in xs if x is not None]
            return round(st.mean(xs), 1) if xs else None
        print("\n" + "=" * 64)
        print(f"{'组别':<12}{'fidelity':>10}{'盲评':>8}{'重合LCS':>9}{'覆盖%':>8}")
        out = {}
        for a, d in R.items():
            out[a] = {"fidelity": avg(d["fid"]), "judge": avg(d["judge"]),
                      "overlap_lcs": avg(d["ov_lcs"]), "overlap_cover_pct": round((avg(d["ov_cov"]) or 0) * 100, 1)}
            print(f"{a:<12}{str(out[a]['fidelity']):>10}{str(out[a]['judge']):>8}{str(out[a]['overlap_lcs']):>9}{out[a]['overlap_cover_pct']:>8}")
        json.dump({"book": BOOK, "result": out, "samples": samples},
                  open(os.path.join(HERE, "ablation_search_v2_results.json"), "w"), ensure_ascii=False, indent=2)
        print("\n结果+样本落 ablation_search_v2_results.json")
        print("判读:C 盲评显著>B 且重合不高 → agentic 公平复赛翻盘;否则 push 仍胜,agentic 确为过度设计。")


if __name__ == "__main__":
    main()
