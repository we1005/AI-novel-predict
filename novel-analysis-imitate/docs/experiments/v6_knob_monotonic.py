"""V6(backlog #7)· 旋钮是否"可预测、可微调" —— live 单调性验证。

固定一轴、扫另一轴,看对应评分轴是否随旋钮**单调**变化、且对**另一轴无明显串扰**:
  - 求异度 novelty ∈ {15,50,85}(强度固定 50):期望 新鲜↑、套路↓ 单调;克味基本稳。
  - 类型强度 genre_strength ∈ {15,50,85}(求异固定 50):期望 克味↑ 单调;套路/新鲜基本稳。
用已存模板「克苏鲁维多利亚」。每轴一次主题、3 档各出一段,裁判盲打 克味/套路/新鲜(3 段同评一次,去位置偏差靠 shuffle)。

跑:backend/.venv/bin/python novel-analysis-imitate/docs/experiments/v6_knob_monotonic.py
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

SLUG = "克苏鲁维多利亚"
TOPIC_N = "码头守夜人发现潮水退去后,礁石上多了一扇门"
TOPIC_G = "钟表匠的工坊里,一只新送来的怀表在午夜自己走了起来"


def _gen(template: dict, topic: str, gs: int, nv: int) -> str:
    sp = gt.render_system_prompt(template, genre_strength=gs, novelty=nv)
    r = llm.call(agent="draft.writer", model=MODEL_STRONG,
                 system=f"你是小说家。严格按以下配方写约 420 字中文场景,不写标题、直接正文。\n{sp}",
                 messages=[{"role": "user", "content": f"场景:{topic}"}],
                 max_tokens=1300, temperature=0.85)
    return (r.text or "").strip()


def _judge3(topic: str, segs: dict[str, str]) -> dict:
    keys = list(segs.keys()); random.shuffle(keys)
    labels = ["甲", "乙", "丙"]
    shown = {labels[i]: keys[i] for i in range(len(keys))}
    body = "\n\n".join(f"【{labels[i]}】\n{segs[keys[i]][:1200]}" for i in range(len(keys)))
    sys = ("你是克苏鲁题材编辑。三段同主题文字(甲/乙/丙)。对**每段**打分,只输出 JSON:"
           '{"甲":{"克味":0-100,"套路":0-100,"新鲜":0-100},"乙":{...},"丙":{...}}'
           "(套路分越高=越陈词滥调)")
    r = llm.call(agent="draft.review.style", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": body}], max_tokens=600, temperature=0.2)
    try:
        from json_repair import repair_json
        v = json.loads(repair_json(re.sub(r"```json|```", "", r.text or ""))) or {}
    except Exception:
        v = {}
    # 映射回真实档位 key
    return {shown[lab]: v.get(lab, {}) for lab in shown}


def _mono(vals: list[float]) -> str:
    if vals[0] < vals[1] < vals[2]: return "单调↑"
    if vals[0] > vals[1] > vals[2]: return "单调↓"
    if vals[0] <= vals[1] <= vals[2]: return "非降"
    if vals[0] >= vals[1] >= vals[2]: return "非升"
    return "非单调"


def main() -> int:
    rec = ps.get_genre_template(SLUG)
    if not rec:
        print(f"模板 {SLUG} 不存在,先抽取"); return 1
    t = rec["template"]

    print("== 求异度扫描(强度固定 50;期望 新鲜↑ 套路↓,克味稳)==", flush=True)
    segN = {f"nv{nv}": _gen(t, TOPIC_N, 50, nv) for nv in (15, 50, 85)}
    sN = _judge3(TOPIC_N, segN)
    for k in ("nv15", "nv50", "nv85"):
        c = sN.get(k, {}); print(f"  {k}: 克味={c.get('克味')} 套路={c.get('套路')} 新鲜={c.get('新鲜')}", flush=True)
    fresh = [sN[k].get("新鲜", 0) for k in ("nv15", "nv50", "nv85")]
    routine = [sN[k].get("套路", 0) for k in ("nv15", "nv50", "nv85")]
    kw = [sN[k].get("克味", 0) for k in ("nv15", "nv50", "nv85")]
    print(f"  → 新鲜 {fresh} {_mono(fresh)} | 套路 {routine} {_mono(routine)} | 克味(串扰?) {kw} {_mono(kw)}", flush=True)

    print("\n== 类型强度扫描(求异固定 50;期望 克味↑,套路/新鲜稳)==", flush=True)
    segG = {f"gs{gs}": _gen(t, TOPIC_G, gs, 50) for gs in (15, 50, 85)}
    sG = _judge3(TOPIC_G, segG)
    for k in ("gs15", "gs50", "gs85"):
        c = sG.get(k, {}); print(f"  {k}: 克味={c.get('克味')} 套路={c.get('套路')} 新鲜={c.get('新鲜')}", flush=True)
    kw2 = [sG[k].get("克味", 0) for k in ("gs15", "gs50", "gs85")]
    routine2 = [sG[k].get("套路", 0) for k in ("gs15", "gs50", "gs85")]
    fresh2 = [sG[k].get("新鲜", 0) for k in ("gs15", "gs50", "gs85")]
    print(f"  → 克味 {kw2} {_mono(kw2)} | 套路(串扰?) {routine2} {_mono(routine2)} | 新鲜(串扰?) {fresh2} {_mono(fresh2)}", flush=True)

    print("\n判读:目标轴单调(新鲜↑/套路↓ 随求异;克味↑ 随强度)= 旋钮可控;非目标轴大幅变动 = 有串扰。n=1主题/轴,指示性。", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
