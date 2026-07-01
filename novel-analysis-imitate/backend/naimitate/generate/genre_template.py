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

# 模板部件。语义层(V1:纯语义)+ 句法层(句法层审查):
# - syntactic_patterns:题材**跨作者共有**的惯用句式/翻译腔(只在多作者同题材蒸馏时产出,见 V1 张力化解)。
# - cliche_sentence_templates:该题材最该避免的**套路句式 slot 模板**(句式+词序,如「<人物>的<眼>+寒芒一闪」)。
_FIELDS = ("imagery", "motifs", "worldview_lexicon", "atmosphere", "flavor_recipe",
           "anti_patterns", "syntactic_patterns", "cliche_sentence_templates")


def _slugify(name: str) -> str:
    s = re.sub(r"\s+", "-", (name or "").strip())
    s = re.sub(r"[^\w一-鿿-]", "", s)
    return s or "genre"


# 抽样默认策略:**按字数比例 + 全书均匀铺开**(非按章节;修"长章少/短章多"偏差 + 只取开头段的偏差)。
# 每本预算 = clamp(ratio×该书字数, min_chars, max_chars);全书均匀取 spread 段。min==max 即"等量模式"。
SAMPLE_DEFAULTS = {"ratio": 0.005, "min_chars": 2500, "max_chars": 8000, "spread": 6}


def _sample(slug: str, cfg: dict | None = None) -> str:
    c = {**SAMPLE_DEFAULTS, **(cfg or {})}
    ratio = max(0.0001, min(0.2, float(c["ratio"])))
    lo = max(500, int(c["min_chars"]))
    hi = max(lo, int(c["max_chars"]))
    spread = max(1, min(20, int(c["spread"])))
    with book_scope(slug):
        with get_engine().begin() as conn:
            rows = conn.execute(_sql("SELECT body FROM chapter_fts ORDER BY chapter")).all()
    full = "\n".join((r[0] or "") for r in rows)
    n = len(full)
    if n == 0:
        return ""
    target = max(lo, min(hi, int(n * ratio)))
    if target >= n:
        return full[:hi]
    seg = max(200, target // spread)
    out = []
    for i in range(spread):                       # 全书按字符位置均匀取 spread 段
        center = int(n * (i + 0.5) / spread)
        start = max(0, min(n - seg, center - seg // 2))
        out.append(full[start:start + seg])
    return "\n…\n".join(out)


def _band(v: int) -> int:
    """0-100 → 0/1/2 三档(低/中/高)。"""
    v = max(0, min(100, int(v)))
    return 0 if v < 34 else (1 if v < 67 else 2)


def render_system_prompt(template: dict, *, genre_strength: int = 70, novelty: int = 60,
                         anti_cliche: bool | None = None, inject_syntax: bool = False) -> str:
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

    # 句法层①:题材惯用句式(正向,受类型强度;轻触档不渲以保持克制)
    # ⚠ inject_syntax 默认 False:V_syntax 实测**把句法层注入提示词反而更套路、更不新鲜**
    #   (套路句式逐条列入=反向 priming;题材句式正向推=prose 变重)。故默认不注入,恢复 V_genre 验证的好行为;
    #   抽取/展示/确定性 detector 仍保留。正确用法应是"生成后 linter"而非 in-prompt,见 docs/V_syntax 结论。
    syn = t.get("syntactic_patterns")
    if inject_syntax and syn and gb >= 1:
        def _syn1(i):
            return i if isinstance(i, str) else f"{i.get('rule', '')}({i.get('example', '')})"
        rendered = ";".join(_syn1(i) for i in (syn if isinstance(syn, list) else [syn]) if i)
        if rendered:
            parts.append("【题材句式】适度运用该题材惯用句式/语序(题材味的句法层,勿生硬堆砌):" + rendered + "。")

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

        # 句法层②:套路句式负面清单(受求异度;大胆档=硬禁用+同章不重复)
        # 同上:inject_syntax 默认 False(实测列举套路句式 → 反向 priming,套路反升)。
        clich = t.get("cliche_sentence_templates") if inject_syntax else None
        if clich:
            ct = ";".join(str(c) for c in (clich if isinstance(clich, list) else [clich]) if c)
            if ct:
                parts.append(
                    ("【句式负面清单·硬禁用】严禁下列套路句式模板**及其同构变体**(出稿自查,命中即改写),同章勿重复任一句式:" + ct + "。")
                    if nb >= 2 else
                    ("【句式负面清单】尽量避开下列套路句式模板及其同构变体:" + ct + "。"))
    return "\n".join(parts)


def _distill(samples: dict[str, str]) -> tuple[dict, float]:
    blob = "\n\n".join(f"【{k}】\n{v}" for k, v in samples.items())
    multi = len(samples) > 1
    # 句法字段:syntactic_patterns 只在**多作者同题材**(multi)时要,以保证抽的是"跨作者收敛的题材句式"
    # 而非某作者私货(化解 V1"结构=作者层"张力);单作者样本不抽题材句式。
    syn_clause = (
        "、syntactic_patterns(该题材**多家作者共有**的惯用句式/翻译腔规则,数组;"
        "每条形如「规则 — 例句」,点名句法操作:状语/介词短语前置、长定语堆叠、"
        "西式连接词(如此…以至于/与其说…不如说)、判断句式等;**只收多家都用的句式,不收某一家的私有节奏**)"
        if multi else ""
    )
    sys = (
        f"你是题材分析师。下面是 {len(samples)} 部"
        f"{'**不同作者**的同题材作品' if multi else '作品'}节选。"
        f"请{'只提炼它们**共同**的' if multi else '提炼其'}**题材语义层 + 句法层**"
        "(语义层不要任何作者私有的句长/段落/标点等**因人而异**的结构习惯;但题材**跨作者共有**的句式/翻译腔属于题材层,要抽)。"
        "只输出 JSON,字段:imagery(核心意象,数组)、motifs(反复母题/套路,数组)、"
        "worldview_lexicon(世界观元件与专有语汇,数组)、atmosphere(氛围情绪基调,一句话)、"
        "flavor_recipe(该题材的'味道'要诀,1-2 句)、anti_patterns(最该避免的**词汇级**陈词,数组)"
        + syn_clause +
        "、cliche_sentence_templates(该题材最该避免的**套路句式模板**,数组;"
        "每条是**句式+词序模板**而非单词,用尖括号标可替换处,并给括号变体,"
        "如「<人物>的<眼睛>+寒芒一闪(变体:眸光一厉/眼底精光一闪)」「<反派>冷笑一声」;"
        "**尽量取语料里真出现过的高频套路**,孤例不算)。"
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


def cliche_lint(text: str, cliche_templates: list[str], *, max_tokens: int = 1600) -> tuple[str, float]:
    """生成**后** linter:只改写命中套路句式模板的句子,其余原样。
    这是句法层的**正确接法**(V_syntax 实测:把套路清单塞进生成提示=反向 priming,套路反升;
    放到生成后做定向去套路则不污染创作)。无命中模板则原样返回(零成本)。"""
    if not text or not cliche_templates:
        return text, 0.0
    tpl = "；".join(str(c) for c in cliche_templates if c)
    sys = (
        "你是中文文字编辑。下面给你一段小说正文和一份'套路句式模板'清单。"
        "任务:**只把正文里命中这些套路句式(或其同构变体)的句子,改写成不落俗套、贴合上下文的表达**;"
        "其余句子**一字不改**。保持情节、人物、信息量、长度大致不变,不要新增情节。直接输出改写后的完整正文,不要解释。\n"
        f"【套路句式模板清单】{tpl}"
    )
    r = llm.call(agent="draft.review.style", model=MODEL_STRONG, system=sys,
                 messages=[{"role": "user", "content": text}],
                 max_tokens=max_tokens, temperature=0.6)
    out = (r.text or "").strip()
    return (out or text), r.cost_usd


def extract_genre_template(name: str, source_slugs: list[str], *,
                           slug: str | None = None, sample: dict | None = None) -> dict:
    """从一组同题材书抽 genre_template 并保存。返回保存后的记录(含 system_prompt)。
    sample:抽样策略(按字数比例+全书均匀铺开),None 则用已存默认/内置默认。"""
    if not source_slugs:
        raise ValueError("source_slugs 不能为空")
    cfg = {**SAMPLE_DEFAULTS, **(project_store.get_genre_sample_config() or {}), **(sample or {})}
    samples = {}
    for s in source_slugs:
        txt = _sample(s, cfg)
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
