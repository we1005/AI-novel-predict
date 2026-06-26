"""基因组 vs 基线 对比评测(eval_protocol 落地)。

对照:同一章大纲,A=基线(StyleProfile 单段总结 + 范文 few-shot),B=基因组 system-prompt。
用同一 writer 模型/温度各生成一段,然后:
  客观:fingerprint_from_text 量两稿 + 与原著章对比确定性维度(弱断言/叠词等),算偏差;
  主观:交给 workflow 的 7 维 LLM 盲评(本模块只产生稿,评委在 workflow 里跑)。
"""
from __future__ import annotations

import json
from datetime import datetime

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from sqlalchemy import select  # noqa: E402
from app.config import MODEL_STRONG  # noqa: E402
from app.db import session_scope, book_scope  # noqa: E402
from app.llm import client as llm  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402
from app.memory.models import StyleProfile  # noqa: E402
from . import models as M  # noqa: E402
from . import _fingerprint as FP  # noqa: E402
from . import _sampling as S  # noqa: E402


def _baseline_prompt() -> str:
    """基线:StyleProfile 单段总结 + 几段范文(原方法)。"""
    with session_scope() as s:
        sp = s.query(StyleProfile).order_by(StyleProfile.id.desc()).first()
        summary = (sp.summary if sp else "") or ""
        ex = sp.scene_exemplars_json if sp else None
    exs = []
    if isinstance(ex, dict):
        exs = list(ex.values())[:3]
    elif isinstance(ex, list):
        exs = ex[:3]
    block = "\n\n".join(str(e)[:400] for e in exs)
    return f"# 文风要求(模仿以下作者)\n{summary}\n\n# 文风范文(照此笔触)\n{block}"


def _genome_prompt() -> str:
    with session_scope() as s:
        row = s.get(M.AnalysisCard, "genome")
    return ((row.card_json or {}).get("system_prompt") if row else "") or ""


def _write(system: str, brief: str, word_target: int = 1200) -> str:
    resp = llm.call(agent="analysis.worldview", model=MODEL_STRONG,
                    system=[{"type": "text", "text": system +
                             "\n\n严格遵循上述文风/架构要求,直接写正文,不要解释。"}],
                    messages=[{"role": "user", "content":
                               f"按以下大纲写一章(约{word_target}字):\n{brief}"}],
                    max_tokens=3000, temperature=0.7)
    return resp.text or ""


def run_eval(slug: str, *, briefs: list[str] | None = None) -> dict:
    """对每个 brief 各生成 A(基线)/B(基因组),算客观指纹偏差。返回稿件+偏差,供 workflow 盲评。"""
    with book_scope(slug):
        init_schema()
        base_sys = _baseline_prompt()
        gen_sys = _genome_prompt()
        if not gen_sys:
            return {"error": "基因组未生成 — 先 run_genome"}
        # 默认 briefs:取代表场景的真实章作为命题(覆盖打斗/悬疑/煽情/转场)
        if not briefs:
            briefs = []
            by = S.sample_by_scene(per_type=1, scene_types=["大高潮", "悬疑惊悚", "煽情", "转场"])
            for st, reps in by.items():
                if reps:
                    briefs.append(f"[{st}] {reps[0].get('summary') or ('第%d章' % reps[0]['chapter'])}")
        # 原著指纹(确定性子集,作标尺)
        src_fp = FP.fingerprint_from_text(FP.full_corpus_text())
        results = []
        for br in briefs:
            A = _write(base_sys, br)
            B = _write(gen_sys, br)
            fa, fb = FP.fingerprint_from_text(A), FP.fingerprint_from_text(B)
            def dev(f):
                return {k: round(abs((f.get(k, 0)) - (src_fp.get(k, 0))), 2) for k in src_fp}
            results.append({
                "brief": br,
                "baseline_text": A, "genome_text": B,
                "src_fp": src_fp, "baseline_fp": fa, "genome_fp": fb,
                "baseline_dev": dev(fa), "genome_dev": dev(fb),
            })
        # 客观汇总:谁的确定性指纹更接近原著(偏差和更小者胜)
        def total_dev(key):
            return round(sum(sum(r[key].values()) for r in results), 2)
        objective = {
            "baseline_total_dev": total_dev("baseline_dev"),
            "genome_total_dev": total_dev("genome_dev"),
            "winner_objective": "genome" if total_dev("genome_dev") < total_dev("baseline_dev") else "baseline",
        }
        out = {"slug": slug, "n_briefs": len(briefs), "objective": objective, "results": results}
        # 落库存档
        with session_scope() as s:
            row = s.get(M.AnalysisCard, "genome.eval")
            if not row:
                row = M.AnalysisCard(category="genome.eval"); s.add(row)
            row.card_json = {"objective": objective, "briefs": briefs,
                             "samples": [{"brief": r["brief"],
                                          "baseline": r["baseline_text"][:1200],
                                          "genome": r["genome_text"][:1200]} for r in results],
                             "ran_at": datetime.utcnow().isoformat()}
    return out
