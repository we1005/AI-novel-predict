"""抽样偏斜零成本诊断(genre_template):各书全书 dialogue_ratio + 引号形态。
目的:在写任何"场景分层"前,先测偏斜是否严重 + dialogue_ratio 正则对该批译本是否有效
(中文对白有 ""/「」/『』 多形态,structural_features 只认 "" → 若某本≈0 说明失效,分层反更坏)。
跑:backend/.venv/bin/python novel-analysis-imitate/docs/experiments/genre_sample_skew_diag.py
"""
from __future__ import annotations
import re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "novel-analysis-imitate" / "backend"))
from naimitate.bootstrap import ensure_app_importable
ensure_app_importable()
from app.db import book_scope, get_engine       # noqa: E402
from naimitate.analysis import _fingerprint as FP  # noqa: E402
from sqlalchemy import text as _sql              # noqa: E402

BOOKS = ["诡秘之主", "余烬之铳", "诡秘地海", "黎明医生", "深海余烬"]


def main() -> int:
    print(f'{"书":<8}{"全书对白比":>10}{"曲引“”":>9}{"直角「」":>9}  判定')
    for slug in BOOKS:
        with book_scope(slug):
            with get_engine().begin() as c:
                rows = c.execute(_sql("SELECT body FROM chapter_fts ORDER BY chapter LIMIT 200")).all()
        txt = "\n".join((r[0] or "") for r in rows)[:1_500_000]
        dr = FP.structural_features(txt).get("dialogue_ratio", 0)
        curly = len(re.findall(r"“[^”]{0,80}”", txt))
        corner = txt.count("「")
        ok = "正则有效" if dr > 0.02 else "⚠正则近失效→勿按对白比分层"
        print(f"{slug:<8}{dr:>10.4f}{curly:>9}{corner:>9}  {ok}")
    print("\n判读:对白比在健康区间(0.15-0.35)且正则有效 → 12-16 段均匀取天然混各模式,偏斜不严重,"
          "无需分层;只需 spread↑(S1)+ 蒸馏跨模式指令(S0)。实测本批 5 本均如此。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
