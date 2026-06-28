"""V3(backlog #3)· 多作者融合会不会变粥 —— live 实验。

问题:把 N 个**声音不同**的作者融成一个模板再写,读者读到的是
  (赢)新自洽腔调 / (串味)能逐一辨认的拼贴 / (变粥)谁都不像的平均?
并验证 brainstorm 的解法:**结构化融合(分轨+配额)** 是否优于 **朴素融合(直接融成一种)**。

选两个差异大的声音:余烬之铳(克苏鲁蒸汽朋克) × 天之炽-江南(江南史诗奇幻)。
两臂:
  A 朴素融合 = "把这两种风格融成一种"
  B 结构化融合 = 分轨:句式/节奏骨架取一家,意象/语汇风味取另一家,目标"新自洽腔调,不要平均、不要拼贴"
3 主题各出 A/B,裁判(给它两家源风格简述)对每段判桶 + coherence/distinct 评分 + A/B 谁更好。

跑:backend/.venv/bin/python novel-analysis-imitate/docs/experiments/v3_fusion_mush.py
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
from app.config import MODEL_STRONG          # noqa: E402
from sqlalchemy import text as _sql          # noqa: E402

BOOK1 = "余烬之铳"        # 克苏鲁蒸汽朋克
BOOK2 = "天之炽-江南"     # 江南史诗奇幻
TOPICS = [
    "一座边境要塞的黎明,守军发现地平线上出现了不该存在的东西",
    "废弃神殿深处,主角与宿敌就一件圣物对峙",
    "雨夜的市集,一个神秘商人向主角兜售一样危险的货物",
]


def _sample(slug: str, chars: int = 4500) -> str:
    with book_scope(slug):
        with get_engine().begin() as c:
            rows = c.execute(_sql(
                "SELECT body FROM chapter_fts WHERE chapter BETWEEN 20 AND 40 LIMIT 5")).all()
    return ("\n".join(r[0] for r in rows))[:chars]


def _distill(name: str, sample: str) -> str:
    sys = ("你是文风分析师。读节选,提炼该作品的写作风格(意象/修辞/语域/句式/氛围),"
           "压成 150 字内、具体可执行的'风格指令'。只输出指令本身。")
    r = llm.call(agent="style.analyze", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": f"【{name}】\n{sample}"}],
                 max_tokens=500, temperature=0.3)
    return (r.text or "").strip()


def _fuse(d1: str, d2: str, structured: bool) -> str:
    if structured:
        sys = ("你是文风融合师。给定两种**差异很大**的风格 X、Y,做**结构化融合**(非平均):"
               "句式/节奏的骨架主要取 X;意象/语汇/氛围的风味主要取 Y;"
               "目标是产出**一个新的、自洽的腔调**——不要平均成中庸,也不要让人能逐句辨认出哪句是 X 哪句是 Y。"
               "输出融合后的统一'风格指令'(180 字内,具体可执行)。只输出指令。")
    else:
        sys = ("你是文风融合师。把下面两种风格融合成一种,输出融合后的'风格指令'(180 字内)。只输出指令。")
    r = llm.call(agent="style.analyze", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": f"【风格 X】{d1}\n\n【风格 Y】{d2}"}],
                 max_tokens=600, temperature=0.4)
    return (r.text or "").strip()


def _write(directive: str, topic: str) -> str:
    sys = f"你是小说家。严格按风格写约 450 字中文场景,不写标题、直接正文。\n【风格指令】{directive}"
    r = llm.call(agent="draft.writer", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": f"场景:{topic}"}],
                 max_tokens=1400, temperature=0.8)
    return (r.text or "").strip()


def _judge(d1: str, d2: str, topic: str, arms: dict[str, str]) -> dict:
    keys = list(arms.keys()); random.shuffle(keys)
    labels = ["甲", "乙"]
    shown = {labels[i]: keys[i] for i in range(len(keys))}
    body = "\n\n".join(f"【{labels[i]}】\n{arms[keys[i]][:1300]}" for i in range(len(keys)))
    sys = ("你是文风评审。两家源风格:\n"
           f"  源X:{d1[:200]}\n  源Y:{d2[:200]}\n"
           "下面是两段尝试融合 X+Y 的同主题文字(甲/乙)。对**每段**判定它属于哪一桶:"
           "'新自洽'(融出一个新的统一腔调)/ '可辨拼贴'(能逐段认出 X 或 Y,有缝)/ '平均粥'(谁都不像、中庸寡淡)。"
           '只输出 JSON:{"甲":{"bucket":"新自洽|可辨拼贴|平均粥","coherence":0-100,"distinct":0-100},'
           '"乙":{...},"better":"甲|乙","reason":"一句话"}')
    r = llm.call(agent="draft.review.style", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": body}], max_tokens=900, temperature=0.2)
    try:
        from json_repair import repair_json
        v = json.loads(repair_json(re.sub(r"```json|```", "", r.text or ""))) or {}
    except Exception:
        v = {}
    return {"map": shown, "verdict": v}


def main() -> int:
    print("== 提炼两家源风格 ==", flush=True)
    d1 = _distill(BOOK1, _sample(BOOK1))
    d2 = _distill(BOOK2, _sample(BOOK2))
    print(f"[X 余烬之铳] {d1[:120]}...\n[Y 天之炽] {d2[:120]}...", flush=True)
    print("\n== 生成两套融合指令 ==", flush=True)
    fused = {"A朴素": _fuse(d1, d2, structured=False), "B结构化": _fuse(d1, d2, structured=True)}
    for k, v in fused.items():
        print(f"[{k}] {v[:140]}...", flush=True)

    buckets = {"A朴素": {"新自洽": 0, "可辨拼贴": 0, "平均粥": 0},
               "B结构化": {"新自洽": 0, "可辨拼贴": 0, "平均粥": 0}}
    scores = {"A朴素": {"coh": [], "dis": []}, "B结构化": {"coh": [], "dis": []}}
    better = {"A朴素": 0, "B结构化": 0}
    for ti, topic in enumerate(TOPICS):
        print(f"\n===== 主题{ti+1}:{topic} =====", flush=True)
        arms = {arm: _write(fused[arm], topic) for arm in fused}
        res = _judge(d1, d2, topic, arms)
        v, m = res["verdict"], res["map"]
        for shown_label, real in m.items():
            cell = v.get(shown_label) or {}
            b = cell.get("bucket")
            if b in buckets[real]:
                buckets[real][b] += 1
            if isinstance(cell.get("coherence"), (int, float)): scores[real]["coh"].append(cell["coherence"])
            if isinstance(cell.get("distinct"), (int, float)): scores[real]["dis"].append(cell["distinct"])
            print(f"  {real}: 桶={b} coherence={cell.get('coherence')} distinct={cell.get('distinct')}", flush=True)
        bett = m.get(v.get("better"))
        if bett in better: better[bett] += 1
        print(f"  更好={bett} · {v.get('reason','')}", flush=True)

    def avg(xs): return round(sum(xs) / len(xs), 1) if xs else 0
    print("\n========== 汇总 ==========", flush=True)
    for arm in buckets:
        s = scores[arm]
        print(f"{arm}: 桶{buckets[arm]}  coherence均={avg(s['coh'])} distinct均={avg(s['dis'])}", flush=True)
    print(f"更好次数: {better}", flush=True)
    print("\n判读:'平均粥/可辨拼贴'多 → 融合确有变粥/串味风险;若 B结构化 的'新自洽'与 coherence 明显高于 A朴素 → 分轨配额是解药。", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
