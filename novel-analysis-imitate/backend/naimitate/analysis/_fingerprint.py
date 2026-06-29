"""文风指纹(fingerprint_vector)的确定性工具:把文风压成可计算的标量+分布向量,
并提供"原著 vs 生成稿"逐维偏差(KL/余弦/相对误差)→ 客观文体保真度分数。

全部纯代码(零 LLM),供:① 各基因组层的密度/频率兜底(避免 LLM 估值漂移);
② 评测闭环(同一把尺子量产出物)。
"""
from __future__ import annotations

import math
import re
from collections import Counter

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from sqlalchemy import select, text as _sql  # noqa: E402
from app.db import get_engine, session_scope  # noqa: E402
from . import models as M  # noqa: E402

HEDGE = re.compile(r"似乎|仿佛|如同|宛如|好像|大概|也许|约莫")
REDUP = re.compile(r"([一-龥])\1")          # 叠字:呆呆/死死/缓缓
ELLIPSIS_PARA = re.compile(r"(^|\n)\s*[…\.]{2,}\s*(\n|$)")  # 省略号独段


# ---- 句法层确定性维(句法层 MVP;**高特异性、无通配**,避免中文假阳性。先作观测/验证,不默认进 compare)----
# 套路句式锚词对:**同句共现**即算命中(评审:不用 .*通配 防噪声淹没)。可外部传入扩展。
DEFAULT_CLICHE_PAIRS = [
    ("瞳孔", "收缩"), ("嘴角", "勾起"), ("嘴角", "扬起"), ("冷笑", "一声"),
    ("眼底", "寒芒"), ("眼中", "精光"), ("眸", "厉色"), ("后颈", "发凉"),
    ("脊背", "发凉"), ("深吸", "一口气"), ("眼神", "一凛"), ("寒芒", "一闪"),
]
# 翻译腔/西式句法的高特异性标记(只取信噪比高的;砍掉"句首状语/泛被动"等中文假阳性高的)
WESTERN_CONNECTORS = re.compile(r"以至于|与其说|不如说|某种(?:意义|程度)上|换言之|不可名状|难以名状")
ABSTRACT_PASSIVE = re.compile(r"被一种|被某种|所(?:攫住|笼罩|吞没|包裹|淹没|裹挟|支配)")


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"[。!?…\n]", text or "") if s.strip()]


def cliche_hit_density(text: str, pairs: list[tuple[str, str]] | None = None) -> float:
    """套路句式命中频次/千字:每个锚词对**同一句内两词共现**计一次。无通配,假阳性低。"""
    pairs = pairs or DEFAULT_CLICHE_PAIRS
    if not text:
        return 0.0
    hits = sum(1 for s in _sentences(text) for a, b in pairs if a in s and b in s)
    return round(hits / (len(text) / 1000.0), 3)


def long_attributive_density(text: str, min_de: int = 3) -> float:
    """长定语堆叠(翻译腔标志):小句内"的"≥min_de 的小句数 / 千字。"""
    if not text:
        return 0.0
    clauses = [c for c in re.split(r"[,,。!?;;\n]", text) if c.strip()]
    n = sum(1 for c in clauses if c.count("的") >= min_de)
    return round(n / (len(text) / 1000.0), 3)


def syntax_metrics(text: str) -> dict:
    """句法层确定性指纹:套路命中 + 高特异性翻译腔标记。供调试观测 / 评测交叉验证。"""
    kk = (len(text) / 1000.0) or 1.0
    return {
        "cliche_hit_per_kchar": cliche_hit_density(text),
        "western_connector_per_kchar": round(len(WESTERN_CONNECTORS.findall(text or "")) / kk, 3),
        "abstract_passive_per_kchar": round(len(ABSTRACT_PASSIVE.findall(text or "")) / kk, 3),
        "long_attributive_per_kchar": long_attributive_density(text),
    }


# ---- 文本聚合 ----

def scene_bucket_text(beats: list[dict] | None = None) -> dict[str, str]:
    """按 scene_type 把章节正文聚到一起 → {scene_type: 拼接文本}。供分场景密度统计。"""
    from . import _sampling as S
    bs = beats if beats is not None else S.all_beats()
    by: dict[str, list[int]] = {}
    for b in bs:
        if b["scene"]:
            by.setdefault(b["scene"], []).append(b["chapter"])
    out = {}
    with get_engine().begin() as c:
        for st, chs in by.items():
            rows = c.execute(_sql("SELECT body FROM chapter_fts WHERE chapter IN ("
                                  + ",".join(str(int(x)) for x in chs[:60]) + ")")).all()
            out[st] = "\n".join((r[0] or "") for r in rows)
    return out


def full_corpus_text(max_chars: int = 2_000_000) -> str:
    with get_engine().begin() as c:
        rows = c.execute(_sql("SELECT body FROM chapter_fts ORDER BY chapter")).all()
    return "\n".join((r[0] or "") for r in rows)[:max_chars]


# ---- 密度/频率 ----

def density_per_kchar(words: list[str], text: str) -> float:
    if not text:
        return 0.0
    hits = sum(text.count(w) for w in words if w)
    return round(hits / len(text) * 1000, 2)


def regex_per_kchar(pat: re.Pattern, text: str) -> float:
    if not text:
        return 0.0
    return round(len(pat.findall(text)) / len(text) * 1000, 2)


def lexical_density_by_scene(strata: list[dict], beats: list[dict] | None = None) -> dict:
    """对每个词汇层,算它在每种 scene_type 桶里的每千字密度(确定性,兜底 LLM 估值)。"""
    buckets = scene_bucket_text(beats)
    out = {}
    for st in strata:
        layer = st.get("layer") or st.get("name") or "?"
        words = st.get("signature_words") or []
        out[layer] = {scene: density_per_kchar(words, txt) for scene, txt in buckets.items()}
    return out


# ---- 张力控制律 ----

def tension_metrics(beats: list[dict]) -> dict:
    tens = [b["tension"] for b in beats]
    if not tens:
        return {}
    n = len(tens)
    peaks = [i for i in range(1, n - 1) if tens[i] >= 80 and tens[i] >= tens[i - 1] and tens[i] >= tens[i + 1]]
    gaps = [peaks[i + 1] - peaks[i] for i in range(len(peaks) - 1)]
    # 上升斜率:峰前若干章的平均增幅;回落:峰后一章的平均跌幅
    rises, falls = [], []
    for p in peaks:
        if p >= 2:
            rises.append((tens[p] - tens[p - 2]) / 2)
        if p + 1 < n:
            falls.append(tens[p] - tens[p + 1])
    def q(xs, p):
        if not xs:
            return None
        xs = sorted(xs); k = int(p * (len(xs) - 1))
        return xs[k]
    # 进度分桶:前/中/后三段的均张力,看是否慢热
    third = max(1, n // 3)
    seg = [round(sum(tens[i:i + third]) / max(1, len(tens[i:i + third])), 1) for i in (0, third, 2 * third)]
    shape = "慢热上扬" if len(seg) == 3 and seg[2] > seg[0] + 8 else ("前重" if seg and seg[0] > seg[-1] + 8 else "平稳多峰")
    return {
        "avg": round(sum(tens) / n, 1), "max": max(tens),
        "n_peaks": len(peaks),
        "peak_gap_median": q(gaps, 0.5),
        "rise_slope_avg": round(sum(rises) / len(rises), 1) if rises else None,
        "falloff_avg": round(sum(falls) / len(falls), 1) if falls else None,
        "seg_avg_thirds": seg, "profile": shape,
    }


# ---- POV 调度 ----

def pov_schedule_metrics() -> dict:
    with session_scope() as s:
        evs = s.execute(select(M.PovEvent)).scalars().all()
        beats = s.execute(select(M.ChapterBeat)).scalars().all()
    n = len(beats) or 1
    nonprot = sum(1 for b in beats if not b.is_protagonist_pov)
    spans = [e.return_after for e in evs if e.return_after]
    why = Counter(e.why_switch for e in evs if e.why_switch)
    return {
        "nonprotagonist_ratio": round(nonprot / n, 2),
        "switch_count": len(evs),
        "away_span_median": (sorted(spans)[len(spans) // 2] if spans else 0),
        "switch_reasons": dict(why.most_common(6)),
    }


# ---- 指纹对比 ----

def _cosine(a: dict, b: dict) -> float:
    keys = set(a) | set(b)
    va = [float(a.get(k, 0) or 0) for k in keys]
    vb = [float(b.get(k, 0) or 0) for k in keys]
    na = math.sqrt(sum(x * x for x in va)) or 1
    nb = math.sqrt(sum(x * x for x in vb)) or 1
    return round(sum(x * y for x, y in zip(va, vb)) / (na * nb), 3)


def _kl(p: dict, q: dict) -> float:
    keys = set(p) | set(q)
    sp = sum(p.get(k, 0) for k in keys) or 1
    sq = sum(q.get(k, 0) for k in keys) or 1
    out = 0.0
    for k in keys:
        pi = (p.get(k, 0) / sp) or 1e-6
        qi = (q.get(k, 0) / sq) or 1e-6
        out += pi * math.log(pi / qi)
    return round(out, 3)


def compare(fp_src: dict, fp_gen: dict) -> dict:
    """原著指纹 vs 生成稿指纹 → 逐维偏差 + 总保真度分(0-100,越高越像)。"""
    report, penalties = {}, []
    # 标量:相对误差
    for k in ["hedge_per_kchar", "reduplication_per_kchar", "bluntness", "infodump_ratio",
              "avg_sent_len", "sent_len_cv", "para_len_mean", "dialogue_ratio", "comma_per_kchar"]:
        sv, gv = fp_src.get(k), fp_gen.get(k)
        if sv is not None and gv is not None:
            rel = abs(gv - sv) / (abs(sv) + 1e-6)
            report[k] = {"src": sv, "gen": gv, "rel_err": round(rel, 2)}
            penalties.append(min(1.0, rel))
    # 分布:余弦相似(越高越好)
    for k in ["metaphor_vehicle_dist", "hook_grammar_dist", "scene_mix"]:
        sv, gv = fp_src.get(k), fp_gen.get(k)
        if isinstance(sv, dict) and isinstance(gv, dict) and sv and gv:
            cos = _cosine(sv, gv)
            report[k] = {"cosine": cos}
            penalties.append(1 - cos)
    # 词汇密度向量(展平)余弦
    def flat(d):
        out = {}
        for layer, scenes in (d or {}).items():
            if isinstance(scenes, dict):
                for sc, v in scenes.items():
                    out[f"{layer}|{sc}"] = v
        return out
    fs, fg = flat(fp_src.get("lexical_density")), flat(fp_gen.get("lexical_density"))
    if fs and fg:
        cos = _cosine(fs, fg)
        report["lexical_density"] = {"cosine": cos}
        penalties.append(1 - cos)
    fidelity = round(100 * (1 - (sum(penalties) / len(penalties))), 1) if penalties else None
    return {"fidelity_score": fidelity, "dimensions": report}


def structural_features(text: str) -> dict:
    """与基因组层**无关**的确定性结构指纹(句长/句长变异/段长/对白比/逗号密度)。
    动机(红蓝对抗 C1/C5 + E1 实测):原 compare 的分布维多取自基因组自产 schema(循环);
    且主链客观对账只用 3 个正则维,判别力弱。加入这些结构维后,'区分余烬之铳真文 vs 他书'
    的客观 AUC 从 ~0.73 升到 ~0.91,且不依赖基因组,部分破除循环。详见 docs/评测可信度-实测.md。"""
    if not text:
        return {}
    n = len(text); kk = n / 1000.0
    sents = [s for s in re.split(r"[。!?…]", text) if s.strip()]
    slen = [len(s) for s in sents] or [0]
    paras = [p for p in text.split("\n") if p.strip()]
    plen = [len(p) for p in paras] or [0]
    dia = sum(len(m) for m in re.findall(r"“[^”]*”", text))
    mean_s = sum(slen) / len(slen)
    var_s = sum((x - mean_s) ** 2 for x in slen) / len(slen)
    cv = (var_s ** 0.5 / mean_s) if mean_s else 0.0
    return {
        "avg_sent_len": round(mean_s, 2),
        "sent_len_cv": round(cv, 3),
        "para_len_mean": round(sum(plen) / len(plen), 1),
        "dialogue_ratio": round(dia / n, 4),
        "comma_per_kchar": round((text.count(",") + text.count("、")) / kk, 2),
    }


def fingerprint_from_text(text: str) -> dict:
    """对一段生成稿,只用确定性手段算出可对比的指纹子集(用于评测扫产出稿)。"""
    out = {
        "hedge_per_kchar": regex_per_kchar(HEDGE, text),
        "reduplication_per_kchar": regex_per_kchar(REDUP, text),
        "ellipsis_para_per_kchar": regex_per_kchar(ELLIPSIS_PARA, text),
    }
    out.update(structural_features(text))   # 加结构维(与基因组无关,判别力更强)
    return out
