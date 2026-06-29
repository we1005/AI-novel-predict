"""V_syntax2 · 句法层"生成后 linter"是否带增量(修正 V_syntax 的 in-prompt 失败)。

V_syntax 结论:把套路句式清单塞进**生成**提示词 → 反向 priming,套路反升。
正解:干净生成 → **生成后**对命中套路句式的句子做定向改写(cliche_lint),不污染创作。
隔离:同一干净底稿 base,B = lint(base);盲评 base(原稿) vs linted(去套路稿)+ 确定性套路命中。
预期:linted 套路↓、克味/新鲜不掉(改的只是套路句,不动其余)。

跑:backend/.venv/bin/python novel-analysis-imitate/docs/experiments/v_syntax2_linter.py
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "novel-analysis-imitate" / "backend"))

from naimitate.bootstrap import ensure_app_importable
ensure_app_importable()
from app.llm import client as llm           # noqa: E402
from app.config import MODEL_STRONG          # noqa: E402
from naimitate.generate import genre_template as gt   # noqa: E402
from naimitate.project import store as ps    # noqa: E402
from naimitate.analysis._fingerprint import cliche_hit_density   # noqa: E402

SLUG = "克苏鲁维多利亚"
GS, NV = 70, 85
TOPICS = [
    "雨夜的旧书店,店主取出一本不肯标价的书",
    "疗养院顶楼,医生发现一个病人房间的镜子里没有他的倒影",
    "码头海关仓库,查验员打开一只渗出咸腥黏液的木箱",
]


def _gen(template: dict, topic: str) -> str:
    sp = gt.render_system_prompt(template, genre_strength=GS, novelty=NV)  # inject_syntax 默认关
    r = llm.call(agent="draft.writer", model=MODEL_STRONG,
                 system=f"你是小说家。严格按以下配方写约 450 字中文场景,不写标题、直接正文。\n{sp}",
                 messages=[{"role": "user", "content": f"场景:{topic}"}],
                 max_tokens=1400, temperature=0.85)
    return (r.text or "").strip()


def _judge(topic: str, arms: dict[str, str]) -> dict:
    keys = list(arms.keys()); random.shuffle(keys)
    labels = ["甲", "乙"]
    shown = {labels[i]: keys[i] for i in range(len(keys))}
    body = "\n\n".join(f"【{labels[i]}】\n{arms[keys[i]][:1300]}" for i in range(len(keys)))
    sys = ("你是克苏鲁题材编辑。两段同主题文字(甲/乙)。盲评,只输出 JSON:"
           '{"甲":{"克味":0-100,"套路":0-100,"新鲜":0-100},"乙":{...},"better":"甲|乙","reason":"一句话"}'
           "(套路分越高=越陈词滥调/越多烂大街句式)")
    r = llm.call(agent="draft.review.style", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": body}], max_tokens=700, temperature=0.2)
    try:
        from json_repair import repair_json
        v = json.loads(repair_json(re.sub(r"```json|```", "", r.text or ""))) or {}
    except Exception:
        v = {}
    return {shown[lab]: v.get(lab, {}) for lab in shown} | {"_better": shown.get(v.get("better"))}


def main() -> int:
    rec = ps.get_genre_template(SLUG)
    if not rec:
        print("模板不存在"); return 1
    full = rec["template"]
    templates = full.get("cliche_sentence_templates") or []
    print(f"套路句式模板 {len(templates)} 条\n", flush=True)

    agg = {"原稿": {"克味": [], "套路": [], "新鲜": [], "cl": []},
           "去套路(linter)": {"克味": [], "套路": [], "新鲜": [], "cl": []}}
    better = {"原稿": 0, "去套路(linter)": 0}
    for ti, topic in enumerate(TOPICS):
        print(f"===== 主题{ti+1}:{topic} =====", flush=True)
        base = _gen(full, topic)
        linted, _ = gt.cliche_lint(base, templates)
        changed = sum(1 for a, b in zip(base, linted) if a != b)  # 粗略改动量
        arms = {"原稿": base, "去套路(linter)": linted}
        for k in arms:
            agg[k]["cl"].append(cliche_hit_density(arms[k]))
        res = _judge(topic, arms)
        for k in ("原稿", "去套路(linter)"):
            c = res.get(k, {})
            for m in ("克味", "套路", "新鲜"):
                if isinstance(c.get(m), (int, float)): agg[k][m].append(c[m])
            print(f"  {k}: 克味={c.get('克味')} 套路={c.get('套路')} 新鲜={c.get('新鲜')} | 确定性套路={agg[k]['cl'][-1]}", flush=True)
        print(f"  (linter 改动字数≈{changed}) 更好={res.get('_better')}", flush=True)
        b = res.get("_better")
        if b in better: better[b] += 1

    def avg(xs): return round(sum(xs)/len(xs), 1) if xs else 0
    print("\n========== 汇总 ==========", flush=True)
    for k in agg:
        a = agg[k]
        print(f"{k}: 克味={avg(a['克味'])} 套路={avg(a['套路'])} 新鲜={avg(a['新鲜'])} | 确定性套路均={avg(a['cl'])}", flush=True)
    print(f"更好次数: {better}", flush=True)
    print("\n判读:去套路稿 套路↓ 且 克味/新鲜不掉 → 生成后 linter 是句法层正解(vs V_syntax 的 in-prompt 失败)。", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
