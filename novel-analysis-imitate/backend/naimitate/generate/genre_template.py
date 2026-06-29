"""通用类型模板(genre_template)· 抽取 + 渲染 + 保存。

把 V_genre 验证过的那套**固化为产品**:从一组同题材书的**语义层**(意象/母题/世界观语汇/氛围/味道)
抽出一个可保存、可调用的"写作配方",并渲染成可直接喂 writer 的 system_prompt(内建 V2 的求异/留白护栏)。

依据(已实测):
- V1:题材在语义层,结构指纹归作者层 → 模板**纯语义**,不含句长/段落等结构指纹。
- V2:裸取共性会更套路 → system_prompt 内建"强制求异 + 负面清单 + 保持节奏"护栏。
- V_genre:该套语义模板 > 裸 prompt(克味/套路/新鲜三轴全胜)、≥ 贴单作者。
- V5:多书知识应**离线蒸成一个连贯模板**,不要写作时混入多作者生片段。
"""
from __future__ import annotations

import json
import re

from app.config import MODEL_STRONG
from app.db import book_scope, get_engine
from app.llm import client as llm
from sqlalchemy import text as _sql

from ..project import store as project_store

# 模板的语义部件(纯语义;无结构指纹——见 V1 定论)
_FIELDS = ("imagery", "motifs", "worldview_lexicon", "atmosphere", "flavor_recipe", "anti_patterns")


def _slugify(name: str) -> str:
    s = re.sub(r"\s+", "-", (name or "").strip())
    s = re.sub(r"[^\w一-鿿-]", "", s)
    return s or "genre"


def _sample(slug: str, chars: int = 2600) -> str:
    with book_scope(slug):
        with get_engine().begin() as c:
            rows = c.execute(_sql(
                "SELECT body FROM chapter_fts WHERE chapter BETWEEN 15 AND 35 LIMIT 4"
            )).all()
    return ("\n".join(r[0] for r in rows))[:chars]


def _band(v: int) -> int:
    """0-100 → 0/1/2 三档(低/中/高)。"""
    v = max(0, min(100, int(v)))
    return 0 if v < 34 else (1 if v < 67 else 2)


def render_system_prompt(template: dict, *, genre_strength: int = 70, novelty: int = 60,
                         anti_cliche: bool | None = None) -> str:
    """把结构化模板渲染成可直接喂 writer 的 system_prompt。纯函数(可单测)。
    两个旋钮(V6):
      - genre_strength 0-100:类型味浓度(轻触 / 正常 / 浓墨重彩)。
      - novelty 0-100:求异度/去套路强度(稳妥 / 适度求新 / 大胆求异;0=不加护栏)。
    anti_cliche(向后兼容):None=用 novelty;False→novelty=0;True→保持 novelty。"""
    t = template or {}
    if anti_cliche is False:
        novelty = 0
    def _join(x):
        if isinstance(x, list):
            return "、".join(str(i) for i in x if i)
        return str(x or "")
    parts = ["【类型写作配方】"]
    if t.get("imagery"):
        parts.append(f"核心意象池:{_join(t['imagery'])}。")
    if t.get("motifs"):
        parts.append(f"母题/套路:{_join(t['motifs'])}。")
    if t.get("worldview_lexicon"):
        parts.append(f"世界观语汇:{_join(t['worldview_lexicon'])}。")
    if t.get("atmosphere"):
        parts.append(f"氛围基调:{_join(t['atmosphere'])}。")
    if t.get("flavor_recipe"):
        parts.append(f"味道要诀:{_join(t['flavor_recipe'])}。")

    # 旋钮①:类型味浓度
    gb = _band(genre_strength)
    parts.append("【类型强度=" + ("轻触】只点到最核心的几个意象,语言克制,不堆砌设定与术语,题材味淡。"
                 if gb == 0 else "适中】自然融入上述意象与氛围,不喧宾夺主。"
                 if gb == 1 else "浓墨重彩】密集调用上述意象/语汇/氛围,饱和该题材的味道与质感。"))

    # 旋钮②:求异度(0=不加护栏)
    if novelty > 0:
        nb = _band(novelty)
        neg = _join(t.get("anti_patterns")) or "嘴角勾起、空气仿佛凝固、心头一紧 等陈词与 AI 腔"
        parts.append("【写作护栏·求异=" + (
            f"稳妥】优先清晰好读、节奏明快,允许常规写法,不刻意求异(仍尽量避开:{neg})。"
            if nb == 0 else
            f"适度】在常规上略加新意,避免最陈词的表达(尤其:{neg})。"
            if nb == 1 else
            f"大胆】**主动加入独特、出人意料、不落俗套的意象与转折**,极力避免任何套路与 AI 腔(尤其:{neg});"
            "但务必保持情节推进与节奏,勿因求新而拖慢、堆砌或写怪话。"))
    return "\n".join(parts)


def _distill(samples: dict[str, str]) -> tuple[dict, float]:
    blob = "\n\n".join(f"【{k}】\n{v}" for k, v in samples.items())
    multi = len(samples) > 1
    sys = (
        f"你是题材分析师。下面是 {len(samples)} 部"
        f"{'**不同作者**的同题材作品' if multi else '作品'}节选。"
        f"请{'只提炼它们**共同**的' if multi else '提炼其'}**题材语义层**"
        "(**不要**任何作者的句长/段落/标点等结构习惯——那是作者指纹,不是题材)。"
        "只输出 JSON,字段:imagery(核心意象,数组)、motifs(反复母题/套路,数组)、"
        "worldview_lexicon(世界观元件与专有语汇,数组)、atmosphere(氛围情绪基调,一句话)、"
        "flavor_recipe(该题材的'味道'要诀,1-2 句)、anti_patterns(写这类最该避免的套路/陈词,数组)。"
    )
    r = llm.call(agent="style.analyze", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": blob}],
                 max_tokens=1200, temperature=0.3)
    raw = r.text or ""
    try:
        from json_repair import repair_json
        data = json.loads(repair_json(re.sub(r"```json|```", "", raw))) or {}
    except Exception:
        data = {}
    template = {k: data.get(k) for k in _FIELDS if data.get(k) is not None}
    return template, r.cost_usd


def extract_genre_template(name: str, source_slugs: list[str], *,
                           slug: str | None = None, sample_chars: int = 2600) -> dict:
    """从一组同题材书抽 genre_template 并保存。返回保存后的记录(含 system_prompt)。"""
    if not source_slugs:
        raise ValueError("source_slugs 不能为空")
    samples = {}
    for s in source_slugs:
        txt = _sample(s, sample_chars)
        if txt and len(txt) > 500:
            samples[s] = txt
    if not samples:
        raise ValueError("所有来源书都取不到语料(请先切分这些书)")
    template, cost = _distill(samples)
    if not template:
        raise RuntimeError("抽取失败:模型未产出有效模板 JSON")
    system_prompt = render_system_prompt(template, anti_cliche=True)
    return project_store.save_genre_template(
        slug or _slugify(name), name, template=template, system_prompt=system_prompt,
        source_slugs=list(samples.keys()), cost_usd=cost,
    )


def preview(slug: str, topic: str, *, genre_strength: int = 70, novelty: int = 60,
            max_tokens: int = 1400) -> dict:
    """用模板写一段样例(证明'可调用')。按旋钮(V6)**实时重渲** system_prompt,而非用存好的默认。"""
    rec = project_store.get_genre_template(slug)
    if not rec:
        raise ValueError(f"genre_template {slug!r} 不存在")
    sp = render_system_prompt(rec.get("template") or {},
                              genre_strength=genre_strength, novelty=novelty)
    r = llm.call(agent="draft.writer", model=MODEL_STRONG,
                 system=f"你是小说家。严格按以下配方写约 450 字中文场景,不写标题、直接正文。\n{sp}",
                 messages=[{"role": "user", "content": f"场景:{topic}"}],
                 max_tokens=max_tokens, temperature=0.85)
    return {"slug": slug, "topic": topic, "genre_strength": genre_strength, "novelty": novelty,
            "system_prompt": sp, "text": (r.text or "").strip(), "cost_usd": r.cost_usd}
