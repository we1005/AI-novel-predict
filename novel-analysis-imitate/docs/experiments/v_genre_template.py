"""V_genre · 从 5 本同题材不同作者的书抽"克苏鲁维多利亚类型模板",验它能否产出"够克味"的文字。

整合 V1/V2/V3 结论:
- V1:题材在**语义层**(意象/母题/世界观/语汇),不在结构指纹 → 模板**纯语义**抽取。
- V2:纯共性会更套路 → 模板生成带"强制求异/留白"。
3 臂 × 3 主题盲评:
  A 类型模板   = 5 书语义共性模板(含求异指令)——我们系统的产物
  B 朴素prompt = "用克苏鲁维多利亚风格写"——没我们系统时用户默认能得到的
  C 单作者     = 仅贴诡秘之主的风格——"贴一个名作者" vs "通用模板"
裁判(给克苏鲁维多利亚 rubric)对每段评:克味(题材契合 0-100)/套路(0-100,越高越套路)/新鲜(0-100),并选各项最佳。

跑:backend/.venv/bin/python novel-analysis-imitate/docs/experiments/v_genre_template.py
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

GENRE_BOOKS = ["诡秘之主", "余烬之铳", "诡秘地海", "黎明医生", "深海余烬"]  # 5 不同作者同题材
SINGLE = "诡秘之主"
TOPICS = [
    "深夜,一位调查员叩响雾中老宅的门,来访的目的与房中之物都不宜言明",
    "港口仓库的地下,主角发现一台不该运转的机器仍在低鸣",
    "教堂晚祷散场后,神父留下一名信徒,谈起一桩与星辰有关的旧事",
]
CLICHE = ["嘴角勾起", "嘴角微微上扬", "不易察觉", "深邃的眼眸", "空气仿佛凝固", "空气凝固",
          "心头一紧", "心中一紧", "眼中闪过一丝", "不知为何", "莫名的", "勾起一抹",
          "深吸一口气", "缓缓地", "宛如", "仿佛过了一个世纪", "脊背发凉", "汗毛倒竖"]
RUBRIC = ("克苏鲁+维多利亚题材标记:不可名状的未知恐惧、理智在真相前的脆弱、维多利亚雾都/工业/蒸汽质感、"
          "神秘学与仪式、旧日/异界存在的暗示、宿命与渺小感、克制阴郁的氛围。")


def _sample(slug: str, chars: int = 2600) -> str:
    with book_scope(slug):
        with get_engine().begin() as c:
            rows = c.execute(_sql(
                "SELECT body FROM chapter_fts WHERE chapter BETWEEN 15 AND 35 LIMIT 4")).all()
    return ("\n".join(r[0] for r in rows))[:chars]


def _distill_genre(samples: dict[str, str]) -> str:
    blob = "\n\n".join(f"【{k}】\n{v}" for k, v in samples.items())
    sys = ("你是题材分析师。下面是 5 部**不同作者**的克苏鲁+维多利亚同题材作品节选。"
           "请只提炼它们**共同的题材语义层**(不要任何单一作者的句式/结构习惯):"
           "① 核心意象池 ② 反复出现的母题/套路 ③ 世界观元件与语汇 ④ 氛围与情绪基调 ⑤ 该题材的'味道'要诀。"
           "压成一段可直接指导写作的'题材模板'(260 字内,具体可执行,列要点)。只输出模板本身。")
    r = llm.call(agent="style.analyze", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": blob}], max_tokens=800, temperature=0.3)
    return (r.text or "").strip()


def _distill_author(name: str, sample: str) -> str:
    sys = ("你是文风分析师。读节选,提炼该作者的写作风格(意象/语域/句式/氛围),"
           "压成 180 字内可执行'风格指令'。只输出指令。")
    r = llm.call(agent="style.analyze", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": f"【{name}】\n{sample}"}],
                 max_tokens=500, temperature=0.3)
    return (r.text or "").strip()


def _write(directive: str, topic: str, anti_cliche: bool) -> str:
    extra = ("\n额外:在该底色上加入独特、出人意料、不落俗套的意象与转折,避免陈词滥调与 AI 腔,"
             "但保持情节推进、勿因求新而拖慢节奏。") if anti_cliche else ""
    sys = f"你是小说家。严格按以下指引写约 450 字中文场景,不写标题、直接正文。\n{directive}{extra}"
    r = llm.call(agent="draft.writer", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": f"场景:{topic}"}],
                 max_tokens=1400, temperature=0.85)
    return (r.text or "").strip()


def _cliche(t): return sum(t.count(c) for c in CLICHE)


def _judge(topic, arms: dict[str, str]) -> dict:
    keys = list(arms.keys()); random.shuffle(keys)
    labels = ["甲", "乙", "丙"]
    shown = {labels[i]: keys[i] for i in range(len(keys))}
    body = "\n\n".join(f"【{labels[i]}】\n{arms[keys[i]][:1400]}" for i in range(len(keys)))
    sys = (f"你是克苏鲁题材编辑。{RUBRIC}\n下面三段同主题文字(甲/乙/丙)。对**每段**按 rubric 评分,"
           "只输出 JSON:"
           '{"甲":{"克味":0-100,"套路":0-100,"新鲜":0-100},"乙":{...},"丙":{...},'
           '"最克味":"甲|乙|丙","最不套路":"甲|乙|丙","reason":"一句话"}'
           "(套路分越高=越陈词滥调)")
    r = llm.call(agent="draft.review.style", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": body}], max_tokens=900, temperature=0.2)
    try:
        from json_repair import repair_json
        v = json.loads(repair_json(re.sub(r"```json|```", "", r.text or ""))) or {}
    except Exception:
        v = {}
    return {"map": shown, "verdict": v}


def main() -> int:
    print("== 抽 5 书语义类型模板 + 单作者风格 ==", flush=True)
    samples = {b: _sample(b) for b in GENRE_BOOKS}
    genre_tpl = _distill_genre(samples)
    author_dir = _distill_author(SINGLE, samples[SINGLE])
    print(f"[类型模板]\n{genre_tpl}\n", flush=True)
    print(f"[单作者 {SINGLE}] {author_dir[:160]}...\n", flush=True)

    DIR = {
        "A模板": f"【克苏鲁维多利亚类型模板】{genre_tpl}",
        "B朴素": "用克苏鲁 + 维多利亚风格写(自行把握该题材的意象与氛围)。",
        "C单作者": f"【风格指令】{author_dir}",
    }
    score = {a: {"克味": [], "套路": [], "新鲜": []} for a in DIR}
    best = {"最克味": {a: 0 for a in DIR}, "最不套路": {a: 0 for a in DIR}}
    cl = {a: 0 for a in DIR}
    for ti, topic in enumerate(TOPICS):
        print(f"\n===== 主题{ti+1}:{topic} =====", flush=True)
        arms = {
            "A模板": _write(DIR["A模板"], topic, anti_cliche=True),    # 模板带求异(V2)
            "B朴素": _write(DIR["B朴素"], topic, anti_cliche=False),
            "C单作者": _write(DIR["C单作者"], topic, anti_cliche=False),
        }
        for a in arms:
            cl[a] += _cliche(arms[a])
        res = _judge(topic, arms); v, m = res["verdict"], res["map"]
        for shown_label, real in m.items():
            cell = v.get(shown_label) or {}
            for k in ("克味", "套路", "新鲜"):
                if isinstance(cell.get(k), (int, float)): score[real][k].append(cell[k])
            print(f"  {real}: 克味={cell.get('克味')} 套路={cell.get('套路')} 新鲜={cell.get('新鲜')}", flush=True)
        for field in best:
            real = m.get(v.get(field))
            if real in best[field]: best[field][real] += 1
        print(f"  最克味={m.get(v.get('最克味'))} 最不套路={m.get(v.get('最不套路'))} · {v.get('reason','')}", flush=True)

    def avg(xs): return round(sum(xs)/len(xs), 1) if xs else 0
    print("\n========== 汇总 ==========", flush=True)
    for a in DIR:
        s = score[a]
        print(f"{a}: 克味均={avg(s['克味'])} 套路均={avg(s['套路'])} 新鲜均={avg(s['新鲜'])} 陈词命中={cl[a]}", flush=True)
    print(f"最克味次数: {best['最克味']}", flush=True)
    print(f"最不套路次数: {best['最不套路']}", flush=True)
    print("\n判读:若 A模板 克味≥C单作者 且 套路≤B朴素 → 通用语义模板既够题材味、又比裸prompt不套路,方向成立;"
          "若 A 克味明显高于 B → 抽取确有增量(非靠 LLM 自带常识)。", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
