"""V1(backlog #2)· 方差当判别器 —— 确定性实验,不烧 token。

验证假设:跨书的文风指纹里,**簇内低方差维 = 共性(类型/作者基因)、簇间高方差维 = 区分信号**。
做法:对多本书算确定性指纹(fingerprint_from_text 的 8 维),按簇(江南同作者多部 / 余烬同题材 / 网文)
算"簇间方差 / 簇内方差"比(类 ANOVA F)。比值高 = 该维能判别簇;某维在江南 3 部(跨子类型)内仍低方差 = 作者基因候选。

诚实边界:理想素材是"同题材不同作者 3+ 本",当前没有;江南簇=同作者跨子类型(测**作者基因**),
余烬簇=同题材(可能同作者)。故本实验验的是"指纹方差能否判别簇 + 哪些维稳定",是 #2 的可答子集。

跑:backend/.venv/bin/python novel-analysis-imitate/docs/experiments/v1_fingerprint_variance.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "novel-analysis-imitate" / "backend"))

from app.books import library          # noqa: E402
from app.db import book_scope          # noqa: E402
from naimitate.analysis import _fingerprint as FP   # noqa: E402

# 簇定义(可调)。新增:克苏鲁维多利亚 5 本**不同作者同题材**(关键——簇内稳定=类型基因)。
CLUSTERS = {
    "克苏鲁维多利亚(5不同作者·同题材)": ["诡秘之主", "余烬之铳", "诡秘地海", "黎明医生", "深海余烬"],
    "江南(同作者·跨子类型)": ["《九州·缥缈录》-江南", "天之炽-江南", "龙族"],
    "网文(对照)": ["末法王座"],
}
SAMPLE_CHARS = 800_000   # 每本取前 ~80万字算指纹(纯字符串/正则,快)
DIMS = ["avg_sent_len", "sent_len_cv", "para_len_mean", "dialogue_ratio",
        "comma_per_kchar", "hedge_per_kchar", "reduplication_per_kchar",
        "ellipsis_para_per_kchar"]


def _fp_for(slug: str) -> dict | None:
    with book_scope(slug):
        try:
            txt = FP.full_corpus_text(max_chars=SAMPLE_CHARS)
        except Exception as e:
            print(f"  !! {slug} 读语料失败: {e}")
            return None
    if not txt or len(txt) < 5000:
        print(f"  !! {slug} 语料过短({len(txt or '')}字),跳过")
        return None
    return FP.fingerprint_from_text(txt)


def _mean(xs): return sum(xs) / len(xs) if xs else 0.0
def _var(xs):
    if len(xs) < 2: return 0.0
    m = _mean(xs); return sum((x - m) ** 2 for x in xs) / len(xs)
def _cv(xs):
    m = _mean(xs); return (_var(xs) ** 0.5 / abs(m)) if m else 0.0


def main() -> int:
    # 1) 算每本指纹
    fps: dict[str, dict] = {}
    for cl, slugs in CLUSTERS.items():
        for slug in slugs:
            fp = _fp_for(slug)
            if fp: fps[slug] = fp
    if not fps:
        print("无可用指纹"); return 1

    # 2) 指纹表
    print("\n===== 各书确定性指纹 =====")
    hdr = "书".ljust(22) + "".join(d[:10].rjust(12) for d in DIMS)
    print(hdr)
    for cl, slugs in CLUSTERS.items():
        for slug in slugs:
            if slug not in fps: continue
            row = slug[:20].ljust(22) + "".join(f"{fps[slug].get(d,0):12.3f}" for d in DIMS)
            print(row)

    # 3) 簇内 CV(只对 ≥2 本的簇)+ 簇间(用各簇均值的离散)
    print("\n===== 各维:簇内 CV(越低=簇内越稳) =====")
    cluster_means: dict[str, dict] = {}
    valid_clusters = {cl: [s for s in slugs if s in fps] for cl, slugs in CLUSTERS.items()}
    for cl, slugs in valid_clusters.items():
        if not slugs: continue
        cluster_means[cl] = {d: _mean([fps[s][d] for s in slugs]) for d in DIMS}
    for cl, slugs in valid_clusters.items():
        if len(slugs) < 2:
            print(f"[{cl}] 仅 {len(slugs)} 本,跳过簇内CV"); continue
        cvs = {d: _cv([fps[s][d] for s in slugs]) for d in DIMS}
        print(f"[{cl}] " + "  ".join(f"{d[:8]}={cvs[d]:.2f}" for d in DIMS))

    # 4) 判别力:簇间方差 / 平均簇内方差(类 F);高=该维能区分簇
    print("\n===== 各维判别力 F≈簇间方差/平均簇内方差(高=可判别簇)=====")
    multi = {cl: s for cl, s in valid_clusters.items() if len(s) >= 2}  # 簇内方差需 ≥2
    fstats = {}
    for d in DIMS:
        between = _var([cluster_means[cl][d] for cl in valid_clusters if valid_clusters[cl]])
        within_list = [_var([fps[s][d] for s in multi[cl]]) for cl in multi]
        within = _mean(within_list) if within_list else 0.0
        f = (between / within) if within > 1e-9 else float("inf")
        fstats[d] = f
    for d in sorted(DIMS, key=lambda x: -fstats[x]):
        tag = "★强判别" if fstats[d] > 5 else ("·中" if fstats[d] > 1.5 else "  弱/噪声")
        print(f"  {d:24s} F={fstats[d]:8.2f}  {tag}")

    # 5) 基因候选:克苏鲁簇(不同作者)内仍低 CV = **类型基因**;江南簇(同作者)内仍低 CV = **作者基因**
    GENE = [
        ("克苏鲁维多利亚(5不同作者·同题材)", "类型基因候选(不同作者仍稳=题材共性)"),
        ("江南(同作者·跨子类型)", "作者基因候选(跨子类型仍稳=江南签名)"),
    ]
    for cl, desc in GENE:
        slugs = [s for s in CLUSTERS.get(cl, []) if s in fps]
        if len(slugs) < 2:
            continue
        print(f"\n===== {desc} —— {cl}({len(slugs)} 本,CV<0.15)=====")
        for d in DIMS:
            cv = _cv([fps[s][d] for s in slugs])
            if cv < 0.15:
                vals = [round(fps[s][d], 2) for s in slugs]
                print(f"  {d:24s} CV={cv:.3f}  值={vals}")

    print("\n[结论留给人读] F 高的维 = 能判别簇的'共性'维;江南跨子类型仍低CV的维 = 作者基因候选。")
    print("注:comma_per_kchar 只数半角逗号+顿号,中文多全角→可能退化(本身是对生产指纹的一处发现)。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
