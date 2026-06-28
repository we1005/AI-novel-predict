"""V2(backlog #12)· 共性提纯会不会更套路 —— live 实验。

存亡问题:取"最大公约数"做类型模板,会不会反而更陈词滥调/更 AI 腔(因为共性=最套路部分)?
3 臂严谨对照(同题材克苏鲁蒸汽朋克:余烬之铳 + 深海余烬):
  A 纯共性模板   = 两书最大公约数风格描述
  B 单书风格     = 仅余烬之铳(有辨识度的个体,作"个性参照")
  C 共性+留白槽  = 共性底色 + 强制"加入独特、不落俗套的意象/转折,避免陈词"
3 个主题各出 A/B/C 三段(~500字),盲排(套路度↑差 / 追读欲↑好)+ 确定性陈词命中计数。
若 A 比 B 更套路 → "共性提纯丢辨识度/增套路"成立;若 C 追平 B 的新鲜又保题材味 → 留白槽是解药。

跑:backend/.venv/bin/python novel-analysis-imitate/docs/experiments/v2_common_vs_cliche.py
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.books import library          # noqa: E402
from app.db import book_scope, session_scope, get_engine   # noqa: E402
from app.llm import client as llm      # noqa: E402
from app.config import MODEL_STRONG, MODEL_FAST   # noqa: E402
from sqlalchemy import text as _sql    # noqa: E402

GENRE_BOOKS = ["余烬之铳", "深海余烬"]      # 同题材簇
SINGLE_BOOK = "余烬之铳"                    # B 臂个性参照
TOPICS = [
    "雾港码头的深夜,主角等待一艘不该靠岸的船",
    "古宅地窖里,主角第一次直面某种不可名状之物",
    "蒸汽机械工坊内,两个敌对者的对峙与试探",
]
# 确定性陈词/AI腔黑名单(命中越多越套路)
CLICHE = ["嘴角勾起", "嘴角微微上扬", "嘴角扬起", "不易察觉", "深邃的眼眸", "深邃的眼睛",
          "仿佛过了一个世纪", "空气仿佛凝固", "空气凝固", "心头一紧", "心中一紧",
          "眼中闪过一丝", "眼底闪过", "不知为何", "莫名的", "勾起一抹", "一抹微笑",
          "宛如", "仿佛要将", "深吸一口气", "缓缓地", "嘴角浮现"]


def _sample(slug: str, chars: int = 5000) -> str:
    with book_scope(slug):
        with get_engine().begin() as c:
            rows = c.execute(_sql(
                "SELECT body FROM chapter_fts WHERE chapter BETWEEN 20 AND 40 LIMIT 6")).all()
        return ("\n".join(r[0] for r in rows))[:chars]


def _distill(label: str, samples: dict[str, str]) -> str:
    blob = "\n\n".join(f"【{k} 节选】\n{v[:3500]}" for k, v in samples.items())
    sys = (f"你是文风分析师。读下面{'若干同题材作品' if len(samples)>1 else '某作品'}节选,"
           f"提炼出{'它们**共同**的' if len(samples)>1 else '它的'}写作风格要点(意象/修辞/语域/句式/氛围),"
           "压成一段可直接指导写作的'风格指令'(200字内,具体可执行,不要复述情节)。只输出风格指令本身。")
    r = llm.call(agent="style.analyze", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": blob}], max_tokens=600, temperature=0.3)
    return (r.text or "").strip()


def _write(style_directive: str, topic: str, slot: bool) -> str:
    extra = ("\n额外要求:在上述风格底色上,**大胆加入独特、出人意料、不落俗套的意象与转折**,"
             "刻意避免陈词滥调与 AI 腔(如'嘴角勾起''空气仿佛凝固''心头一紧'等)。") if slot else ""
    sys = f"你是小说家。严格按以下风格写一段约 500 字的中文场景,不写标题、直接正文。\n【风格指令】{style_directive}{extra}"
    r = llm.call(agent="draft.writer", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": f"场景主题:{topic}"}],
                 max_tokens=1500, temperature=0.8)
    return (r.text or "").strip()


def _cliche_count(t: str) -> int:
    return sum(t.count(c) for c in CLICHE)


def _rank(topic: str, arms: dict[str, str]) -> dict:
    keys = list(arms.keys()); random.shuffle(keys)
    labels = ["甲", "乙", "丙"]
    shown = {labels[i]: keys[i] for i in range(len(keys))}   # 显示标签 → 真实臂
    body = "\n\n".join(f"【{labels[i]}】\n{arms[keys[i]][:1500]}" for i in range(len(keys)))
    sys = ("你是挑剔的中文小说编辑。下面三段同主题文字(甲/乙/丙)。请盲评,只输出 JSON:"
           '{"least_cliche":"甲|乙|丙(最不套路、最新鲜的)",'
           '"most_cliche":"甲|乙|丙(最陈词滥调/最AI腔的)",'
           '"most_readable":"甲|乙|丙(最有追读欲的)","reason":"一句话"}')
    r = llm.call(agent="draft.review.style", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": body}], max_tokens=800, temperature=0.2)
    try:
        from json_repair import repair_json
        v = json.loads(repair_json(re.sub(r"```json|```", "", r.text or ""))) or {}
    except Exception:
        v = {}
    return {"map": shown, "verdict": v}


def main() -> int:
    print("== 抽样 + 提炼风格指令 ==", flush=True)
    samples = {b: _sample(b) for b in GENRE_BOOKS}
    common = _distill("共性", samples)
    single = _distill("单书", {SINGLE_BOOK: samples[SINGLE_BOOK]})
    print(f"[共性指令] {common[:160]}…\n[单书指令] {single[:160]}…\n", flush=True)

    tally = {"least_cliche": {"A": 0, "B": 0, "C": 0}, "most_cliche": {"A": 0, "B": 0, "C": 0},
             "most_readable": {"A": 0, "B": 0, "C": 0}}
    cl_sum = {"A": 0, "B": 0, "C": 0}
    for ti, topic in enumerate(TOPICS):
        print(f"\n===== 主题{ti+1}:{topic} =====", flush=True)
        arms = {
            "A": _write(common, topic, slot=False),
            "B": _write(single, topic, slot=False),
            "C": _write(common, topic, slot=True),
        }
        for k in arms:
            c = _cliche_count(arms[k]); cl_sum[k] += c
            print(f"  [{k}] 陈词命中={c} 字数={len(arms[k])}", flush=True)
        res = _rank(topic, arms)
        v, m = res["verdict"], res["map"]   # m: 显示标签→真实臂
        for field in tally:
            shown = v.get(field)
            real = m.get(shown)
            if real in tally[field]:
                tally[field][real] += 1
        print(f"  盲评(已映射回真实臂): 最不套路={m.get(v.get('least_cliche'))} "
              f"最套路={m.get(v.get('most_cliche'))} 最追读={m.get(v.get('most_readable'))}", flush=True)
        print(f"    理由:{v.get('reason','')}", flush=True)

    print("\n========== 汇总 ==========", flush=True)
    print(f"确定性陈词命中合计: A纯共性={cl_sum['A']}  B单书={cl_sum['B']}  C共性+留白={cl_sum['C']}", flush=True)
    print(f"盲评 最不套路次数: {tally['least_cliche']}", flush=True)
    print(f"盲评 最套路次数  : {tally['most_cliche']}", flush=True)
    print(f"盲评 最追读次数  : {tally['most_readable']}", flush=True)
    print("\n判读指引:若 A 的'最套路'次数/陈词命中 ≥ B → 共性提纯确实增套路/丢辨识度;"
          "若 C 的'最不套路+最追读'≥ B 且≥A → 留白槽是有效解药。", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
