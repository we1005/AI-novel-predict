"""V5(backlog #4)· 跨书 agentic 检索 vs 单书 —— live 实验。

问题:让写作时的检索从"**所有同题材源书**自取范例",是否比限"单书"更出活(更克味/意象更丰富)?
隔离变量:同一类型模板底色 + 同一组规划查询,**只差检索范围**(单书 余烬之铳 vs 跨 5 本克苏鲁池)。
3 主题各出 单书/跨书 两段,盲评 克味/意象丰富度/质量 + 谁更好。

跑:backend/.venv/bin/python novel-analysis-imitate/docs/experiments/v5_crossbook_retrieval.py
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.db import book_scope, get_engine   # noqa: E402
from app.llm import client as llm           # noqa: E402
from app.config import MODEL_STRONG, MODEL_FAST   # noqa: E402
from app.craft import search as cs          # noqa: E402
from sqlalchemy import text as _sql          # noqa: E402

POOL = ["诡秘之主", "余烬之铳", "诡秘地海", "黎明医生", "深海余烬"]
SINGLE_BOOK = "余烬之铳"
TOPICS = [
    "一场降神会上,媒介开始说出在场所有人都不该知道的事",
    "矿镇深处的巷道里,矿灯照见墙上不属于人类的刻痕",
    "拍卖行的密室,一件裹着绒布的展品让所有买家失语",
]

GENRE_TPL = ("【克苏鲁维多利亚类型模板】核心意象:蒸汽机械/煤气灯/雾都/古神低语/禁忌知识/异变/秘密结社/异常收容物;"
             "母题:接触禁忌致精神污染、表面秩序下的疯狂真相、以调查为名的危险;氛围:压抑疏离、知识即诅咒、个体渺小;"
             "味道:用可理解的蒸汽朋克外壳包裹不可名状内核,在煤气灯下研究深渊的冰冷考究口吻。")


def _plan(topic: str, n: int = 3) -> list[str]:
    sys = (f"为下面的写作主题,列出最多 {n} 条最该去克苏鲁维多利亚原著里检索的'具体意象/场景关键词'"
           "(具体如'降神会通灵''矿道异常刻痕',忌空泛)。"
           "**必须是中文关键词**(原著是中文,英文查不到),每条 4-8 个汉字。"
           "只输出 JSON:{\"q\":[\"中文词\",\"中文词\"]}")
    r = llm.call(agent="draft.review.style", model=MODEL_FAST, system=sys,
                 messages=[{"role": "user", "content": topic}], max_tokens=400, temperature=0.3)
    try:
        from json_repair import repair_json
        d = json.loads(repair_json(re.sub(r"```json|```", "", r.text or ""))) or {}
        return [str(x)[:40] for x in (d.get("q") or [])][:n]
    except Exception:
        return [topic[:30]]


def _search_books(query: str, books: list[str], k_per: int = 1) -> list[dict]:
    out = []
    for slug in books:
        with book_scope(slug):
            try:
                for h in cs.search_corpus(query, k=k_per):
                    out.append({"book": slug, "chapter": h.get("chapter"), "snip": (h.get("snip") or "")[:300]})
            except Exception:
                continue
    return out


def _refs_block(refs: list[dict]) -> str:
    if not refs:
        return "(无检索范例)"
    return "\n".join(f"[{r['book']} 第{r['chapter']}章] {r['snip']}" for r in refs[:6])


def _write(topic: str, refs: list[dict]) -> str:
    sys = (f"你是小说家。按下述类型模板写约 450 字中文场景,不写标题、直接正文。{GENRE_TPL}\n"
           "下面是若干**原著范例片段**,模仿其意象与质感(勿照抄文字):\n" + _refs_block(refs))
    r = llm.call(agent="draft.writer", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": f"场景:{topic}"}],
                 max_tokens=1400, temperature=0.85)
    return (r.text or "").strip()


def _judge(topic: str, arms: dict[str, str]) -> dict:
    keys = list(arms.keys()); random.shuffle(keys)
    labels = ["甲", "乙"]
    shown = {labels[i]: keys[i] for i in range(len(keys))}
    body = "\n\n".join(f"【{labels[i]}】\n{arms[keys[i]][:1300]}" for i in range(len(keys)))
    sys = ("你是克苏鲁题材编辑。两段同主题文字(甲/乙)。盲评,只输出 JSON:"
           '{"甲":{"克味":0-100,"意象丰富":0-100,"质量":0-100},"乙":{...},'
           '"better":"甲|乙","reason":"一句话"}')
    r = llm.call(agent="draft.review.style", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": body}], max_tokens=700, temperature=0.2)
    try:
        from json_repair import repair_json
        v = json.loads(repair_json(re.sub(r"```json|```", "", r.text or ""))) or {}
    except Exception:
        v = {}
    return {"map": shown, "verdict": v}


def main() -> int:
    score = {"单书": {"克味": [], "意象丰富": [], "质量": []},
             "跨书": {"克味": [], "意象丰富": [], "质量": []}}
    better = {"单书": 0, "跨书": 0}
    for ti, topic in enumerate(TOPICS):
        print(f"\n===== 主题{ti+1}:{topic} =====", flush=True)
        queries = _plan(topic)
        print(f"  规划查询: {queries}", flush=True)
        single_refs, cross_refs = [], []
        for q in queries:
            single_refs += _search_books(q, [SINGLE_BOOK], k_per=1)
            cross_refs += _search_books(q, POOL, k_per=1)
        sb = {r["book"] for r in single_refs}; cb = {r["book"] for r in cross_refs}
        print(f"  单书命中 {len(single_refs)} 条(书:{sb}) | 跨书命中 {len(cross_refs)} 条(书:{cb})", flush=True)
        arms = {"单书": _write(topic, single_refs), "跨书": _write(topic, cross_refs)}
        res = _judge(topic, arms); v, m = res["verdict"], res["map"]
        for shown_label, real in m.items():
            cell = v.get(shown_label) or {}
            for kk in ("克味", "意象丰富", "质量"):
                if isinstance(cell.get(kk), (int, float)): score[real][kk].append(cell[kk])
            print(f"  {real}: 克味={cell.get('克味')} 意象丰富={cell.get('意象丰富')} 质量={cell.get('质量')}", flush=True)
        bett = m.get(v.get("better"))
        if bett in better: better[bett] += 1
        print(f"  更好={bett} · {v.get('reason','')}", flush=True)

    def avg(xs): return round(sum(xs)/len(xs), 1) if xs else 0
    print("\n========== 汇总 ==========", flush=True)
    for a in score:
        s = score[a]
        print(f"{a}: 克味均={avg(s['克味'])} 意象丰富均={avg(s['意象丰富'])} 质量均={avg(s['质量'])}", flush=True)
    print(f"更好次数: {better}", flush=True)
    print("\n判读:若跨书 意象丰富/克味 明显高于单书 → '同题材跨书检索池'有价值,值得做;若打平 → 单书已够、跨书非必需。", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
