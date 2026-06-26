"""文风基因组(STYLE GENOME):把作者的写作范式 + 宏观编排架构抽成可复用、可喂给
其它 LLM/Agent 复现该风格的分层结构。补足"单段总结"基线抓不到的三类东西:

  微观范式  : lexicon(词汇分层) / syntax(句式模板) / rhetoric(修辞倾向)
  类型氛围  : atmosphere(蒸汽朋克/克苏鲁等质感"配方":手段→实现→例证)
  场景套路  : scene_routine(每类场面:从哪切入/角度/节拍序列/详略/收尾钩子)
  宏观架构  : macro_arch(伏笔plant→回扣payoff分布/信息计量/张力调制/段落编排模板)
  转移模型  : transition(场景→下一步倾向的马尔可夫矩阵 + plot_function 转移,LSTM/Transformer 类比)

各层存进该书 novel.db 的 analysis_card,category='genome.<layer>';assemble 汇成 'genome'
聚合卡 + 渲染成"喂给另一个 LLM 就能复现风格"的 system-prompt spec。全程 book_scope。
"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime

from ..bootstrap import ensure_app_importable

ensure_app_importable()

from sqlalchemy import select, text as _sql  # noqa: E402
from app.config import MODEL_STRONG  # noqa: E402
from app.db import session_scope, book_scope, get_engine  # noqa: E402
from app.llm import client as llm  # noqa: E402
from app.memory.schema_init import init_schema  # noqa: E402
from . import models as M  # noqa: E402
from . import _sampling as S  # noqa: E402
from . import _fingerprint as FP  # noqa: E402


def _strip(s: str) -> str:
    return re.sub(r"```json|```", "", s or "").strip()


def _loads(resp) -> dict:
    try:
        from json_repair import repair_json
        d = json.loads(repair_json(_strip(resp.text)))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _ask(sys: str, user: str, max_tokens: int = 3500) -> dict:
    resp = llm.call(agent="analysis.worldview", model=MODEL_STRONG,
                    system=[{"type": "text", "text": sys}],
                    messages=[{"role": "user", "content": user[:90000]}],
                    max_tokens=max_tokens, temperature=0.4, response_format={"type": "json_object"})
    return _loads(resp)


def _save(category: str, card: dict) -> None:
    with session_scope() as s:
        row = s.get(M.AnalysisCard, category)
        if not row:
            row = M.AnalysisCard(category=category); s.add(row)
        row.card_json = card
        row.updated_at = datetime.utcnow()


def _blocks(samples: list[dict], n_text: int = 9999) -> str:
    return "\n\n".join(f"【第{x['chapter']}章 · {x.get('scene','')} 张力{x.get('tension','')}】\n{x.get('text','')}"
                       for x in samples[:n_text])


# ───────────────────────── 微观范式 ─────────────────────────

def layer_lexicon(slug: str) -> dict:
    # 分桶取样(每场景类型取代表章),让模型看到"不同场景的用词差异"
    by = S.sample_by_scene(per_type=2)
    blocks = []
    for st, reps in by.items():
        for r in reps[:2]:
            blocks.append(f"【{st}·第{r['chapter']}章】\n{r.get('text','')[:1400]}")
    sys = (
        "你是语料文体学家。阅读分场景的多章节选,提炼该作者的**分层词汇指纹**(可复用调色盘,"
        "不要泛泛,只收原文真出现的词、不许编造)。\n"
        "输出 JSON:{strata:[{layer(语义场id,如 cthulhu_unnameable/steampunk_machine/religion/"
        "sensory_body/military_detective/victorian_daily/emotion), gloss(中文说明), "
        "signature_words:[标志词], collocations:[{head:词, with:[常见搭配]}], "
        "trigger_context(什么场景/时机才用)}], diction(文白雅俗冷硬总体坐标), "
        "avoid:[作者明显回避的廉价/网文词]}。只输出 JSON。"
    )
    card = _ask(sys, "\n\n".join(blocks))
    # 确定性兜底:每层在每种 scene_type 桶里的每千字密度(避免 LLM 估值漂移)
    try:
        card["density_by_scene"] = FP.lexical_density_by_scene(card.get("strata") or [])
    except Exception as e:  # noqa: BLE001
        print(f"[genome.lexicon] density 兜底失败: {str(e)[:80]}", flush=True)
    _save("genome.lexicon", card)
    return card


def layer_syntax(slug: str) -> dict:
    sm = S.spread_sample(n=12)
    sys = (
        "你是句法节奏分析师。提炼该作者的**句式范式**。\n"
        "输出 JSON:{sentence_patterns:[{pattern(句式模板,用占位符如『不是X,而是Y』『动词+短句+独段』), "
        "function(用于什么场景/效果), examples:[2-3 原文例句]}], rhythm(长短句配比与节奏规律), "
        "paragraphing(分段习惯,如独句成段/长段铺陈), punctuation(标点偏好,如破折号/省略号用法)}。只输出 JSON。"
    )
    card = _ask(sys, _blocks(sm))
    _save("genome.syntax", card)
    return card


def layer_rhetoric(slug: str) -> dict:
    sm = S.spread_sample(n=10)
    sys = (
        "你是修辞分析师。提炼该作者的**修辞范式**。\n"
        "输出 JSON:{devices:[{device(比喻/通感/留白/反复/列举/拟人/对照…), tendency(本体喻体偏好、"
        "用在哪、强度), examples:[2-3 原文例]}], imagery_sources:[喻体/意象常取材的领域], "
        "signature_move(最具辨识度的一招修辞)}。只输出 JSON。"
    )
    card = _ask(sys, _blocks(sm))
    _save("genome.rhetoric", card)
    return card


# ───────────────────────── 类型氛围配方 ─────────────────────────

def layer_atmosphere(slug: str) -> dict:
    sm = S.high_tension_sample(n=8)
    # 附带世界观揭示样本,帮助归纳"设定怎么转成质感"
    with session_scope() as s:
        rv = s.execute(select(M.WorldviewReveal).order_by(M.WorldviewReveal.importance.desc()).limit(20)).scalars().all()
    rvtxt = "\n".join(f"- {r.concept}({r.reveal_method}): {r.summary}" for r in rv)
    sys = (
        "你是类型质感工艺分析师。归纳该书的**类型氛围配方**——某种质感(如蒸汽朋克/克苏鲁恐怖/"
        "维多利亚阴郁/悬疑)具体**通过什么手段**营造。\n"
        "输出 JSON:{genres:[{genre(质感名), mechanisms:[{means(手段,如 器物密度/能源-机械隐喻/"
        "侧面烘托/感官失序/回避命名/理智代价/异常日常化/阶级对照), how(具体实现方式), "
        "example:[1-2 原文例证]}]}], golden_rules:[复现该氛围的可操作准则]}。只输出 JSON。"
    )
    card = _ask(sys, _blocks(sm) + "\n\n# 世界观揭示参考\n" + rvtxt, max_tokens=4000)
    _save("genome.atmosphere", card)
    return card


# ───────────────────────── 场景套路 ─────────────────────────

def layer_scene_routine(slug: str) -> dict:
    by = S.sample_by_scene(per_type=2)
    out = {"routines": []}
    for stype, reps in by.items():
        if not reps:
            continue
        sys = (
            f"你是场面调度分析师。下面是该作者写『{stype}』场景的代表章节选。提炼他写这类场景的**套路**。\n"
            "输出 JSON:{opening_move(从哪切入:景物/对话/动作/人物内心/旁白/感官 + 怎么切), "
            "pov_angle(视角与镜头距离), beat_sequence:[该类场景的节拍顺序,如 环境压迫→对峙→爆发→代价], "
            "detail_distribution(详略分配:详写什么、略写什么), ending_hook(收尾/钩子范式), "
            "signature(这类场景最像他的一点)}。只输出 JSON。"
        )
        card = _ask(sys, _blocks(reps), max_tokens=2000)
        card["scene_type"] = stype
        card["sample_chapters"] = [r["chapter"] for r in reps]
        out["routines"].append(card)
    _save("genome.scene_routine", out)
    return out


# ───────────────────────── 宏观架构 ─────────────────────────

def layer_macro_arch(slug: str) -> dict:
    """伏笔 plant→payoff 分布 + 信息计量 + 张力调制 + 段落编排模板(部分确定性 + LLM 归纳)。"""
    with session_scope() as s:
        beats = s.execute(select(M.ChapterBeat).order_by(M.ChapterBeat.chapter)).scalars().all()
        cards = {c.category: c.card_json for c in s.execute(select(M.AnalysisCard)).scalars().all()}
    tens = [b.tension_level or 0 for b in beats]
    # 张力调制:大高潮间距
    climax = [i for i, b in enumerate(beats) if b.scene_type == "大高潮" or (b.tension_level or 0) >= 85]
    climax_gap = round(statistics.mean([climax[i+1]-climax[i] for i in range(len(climax)-1)]), 1) if len(climax) > 1 else None
    bdicts = [{"chapter": b.chapter, "scene": b.scene_type, "tension": b.tension_level or 0,
               "is_protagonist_pov": b.is_protagonist_pov} for b in beats]
    # 伏笔账本:直接复用既有 foreshadowings 表(planted/resolved/type/status)做确定性聚合
    fore_stats = {}
    try:
        with get_engine().begin() as c:
            rows = c.execute(_sql("SELECT planted_chapter,resolved_chapter,type,status FROM foreshadowings")).mappings().all()
        spans = [(r["resolved_chapter"] - r["planted_chapter"]) for r in rows
                 if r["resolved_chapter"] and r["planted_chapter"] and r["resolved_chapter"] > r["planted_chapter"]]
        spans.sort()
        fore_stats = {
            "n": len(rows),
            "resolved": sum(1 for r in rows if r["resolved_chapter"]),
            "open": sum(1 for r in rows if not r["resolved_chapter"]),
            "median_span": (spans[len(spans)//2] if spans else None),
            "long_line_ratio": round(sum(1 for s in spans if s >= 100) / len(spans), 2) if spans else 0,
            "type_dist": dict(Counter((r["type"] or "?") for r in rows).most_common(8)),
        }
    except Exception as e:  # noqa: BLE001
        print(f"[genome.macro_arch] 伏笔聚合失败: {str(e)[:80]}", flush=True)
    determ = {
        "tension_law": FP.tension_metrics(bdicts),       # 峰检测/斜率/回落/峰间距/分段趋势
        "pov_schedule": FP.pov_schedule_metrics(),
        "foreshadow": fore_stats,
        "info_metering": (cards.get("worldview") or {}),  # 信息倾倒率/前载比/手法
        "scene_mix": dict(Counter(b.scene_type for b in beats if b.scene_type)),
        "_legacy_climax_interval": climax_gap,
    }
    # LLM 归纳"段落编排模板"(用速读阶段 + 节拍曲线描述)
    stages = []
    with session_scope() as s:
        for r in s.execute(select(M.SpeedReadStage).order_by(M.SpeedReadStage.stage_index)).scalars().all():
            stages.append(f"{r.chapter_start}-{r.chapter_end} [{r.importance}] {r.title}: {r.one_liner}")
    sys = (
        "你是叙事结构架构师。给你一本书的阶段梗概 + 张力/场景统计。提炼其**宏观编排架构模板**——"
        "可复用、可指导别的作者/模型按同样的结构组织一个新故事。\n"
        "输出 JSON:{act_structure(整体几幕/段落如何起承转合), "
        "stage_template(一个典型阶段内部怎么编排:铺垫→升级→高潮→喘息的占比与顺序), "
        "foreshadow_strategy(伏笔埋设与回扣的节奏:埋多远收、密度), "
        "escalation_logic(冲突/危机如何逐级抬升), "
        "opening_and_ending(开篇怎么抓人、结尾怎么收), reusable_skeleton:[把架构写成可套用的 N 步骨架]}。只输出 JSON。"
    )
    llm_card = _ask(sys, "# 阶段梗概\n" + "\n".join(stages)[:40000] +
                    "\n\n# 统计\n" + json.dumps(determ, ensure_ascii=False), max_tokens=4000)
    card = {"metrics": determ, "templates": llm_card}
    _save("genome.macro_arch", card)
    return card


def layer_transition(slug: str) -> dict:
    """场景类型转移矩阵 + plot_function 转移(确定性,LSTM/Transformer 类比的"状态转移"层)。"""
    with session_scope() as s:
        beats = s.execute(select(M.ChapterBeat).order_by(M.ChapterBeat.chapter)).scalars().all()
    def matrix(seq):
        trans = defaultdict(Counter)
        for a, b in zip(seq, seq[1:]):
            if a and b:
                trans[a][b] += 1
        # 归一成概率
        out = {}
        for a, ctr in trans.items():
            tot = sum(ctr.values())
            out[a] = {b: round(n / tot, 3) for b, n in ctr.most_common()}
        return out
    scene_seq = [b.scene_type for b in beats]
    fn_seq = [b.plot_function for b in beats]
    # 每个状态最可能的下一步(给 LLM/Agent 当"递进倾向"指引)
    scene_tr = matrix(scene_seq)
    top_next = {a: max(d.items(), key=lambda kv: kv[1])[0] for a, d in scene_tr.items() if d}
    card = {
        "scene_transition": scene_tr,
        "plot_function_transition": matrix(fn_seq),
        "most_likely_next": top_next,
        "note": "状态=场景类型/叙事功能;值=转移概率。可据此让生成模型按作者的递进倾向排布下一拍。",
    }
    _save("genome.transition", card)
    return card


# ───────────────────────── 组装 + 渲染 ─────────────────────────

LAYERS = ["lexicon", "syntax", "rhetoric", "atmosphere", "scene_routine", "macro_arch", "transition"]


def run_genome(slug: str, *, layers: list[str] | None = None) -> dict:
    layers = layers or LAYERS
    fns = {"lexicon": layer_lexicon, "syntax": layer_syntax, "rhetoric": layer_rhetoric,
           "atmosphere": layer_atmosphere, "scene_routine": layer_scene_routine,
           "macro_arch": layer_macro_arch, "transition": layer_transition}
    done = {}
    with book_scope(slug):
        init_schema()
        for ly in layers:
            try:
                fns[ly](slug)
                done[ly] = "ok"
                print(f"[genome] {slug} {ly} ok", flush=True)
            except Exception as e:  # noqa: BLE001
                done[ly] = f"err: {str(e)[:80]}"
                print(f"[genome] {slug} {ly} 失败: {str(e)[:100]}", flush=True)
        assemble(slug)
    return {"slug": slug, "layers": done}


def build_fingerprint(slug: str, genome: dict, cards: dict) -> dict:
    """把基因组压成可计算的指纹向量(标量+分布),供客观评测逐维 diff。"""
    fp: dict = {}
    lex = genome.get("lexicon") or {}
    if lex.get("density_by_scene"):
        fp["lexical_density"] = lex["density_by_scene"]
    rhe = genome.get("rhetoric") or {}
    mm = (rhe.get("metaphor_map") or {}).get("vehicle_dist") or rhe.get("vehicle_dist")
    if isinstance(mm, dict):
        fp["metaphor_vehicle_dist"] = mm
    ma = genome.get("macro_arch") or {}
    met = ma.get("metrics") or {}
    fp["scene_mix"] = met.get("scene_mix") or {}
    fp["infodump_ratio"] = (met.get("info_metering") or {}).get("infodump_ratio")
    tl = met.get("tension_law") or {}
    fp["tension_profile"] = tl.get("profile")
    fp["tension_avg"] = tl.get("avg")
    # 全局确定性标量(直接量原文)
    try:
        corpus = FP.full_corpus_text()
        fp["hedge_per_kchar"] = FP.regex_per_kchar(FP.HEDGE, corpus)
        fp["reduplication_per_kchar"] = FP.regex_per_kchar(FP.REDUP, corpus)
    except Exception:
        pass
    sr = genome.get("scene_routine") or {}
    hooks = Counter()
    blunt = []
    for r in (sr.get("routines") or []):
        ex = r.get("exit") or {}
        if ex.get("hook_grammar"):
            hooks[ex["hook_grammar"]] += 1
        if isinstance(r.get("bluntness"), (int, float)):
            blunt.append(r["bluntness"])
    if hooks:
        fp["hook_grammar_dist"] = dict(hooks)
    if blunt:
        fp["bluntness"] = round(sum(blunt) / len(blunt), 1)
    tr = genome.get("transition") or {}
    if tr.get("most_likely_next"):
        fp["scene_transition_topk"] = tr["most_likely_next"]
    return fp


def assemble(slug: str) -> dict:
    """汇总各层 + 指纹向量 + 渲染成可喂给别的 LLM 的 system-prompt spec。"""
    with session_scope() as s:
        cards = {c.category: c.card_json for c in s.execute(select(M.AnalysisCard)).scalars().all()}
    genome = {ly: cards.get(f"genome.{ly}") for ly in LAYERS if cards.get(f"genome.{ly}")}
    fingerprint = build_fingerprint(slug, genome, cards)
    spec = render_spec(slug, genome, cards)
    agg = {"layers_present": list(genome.keys()), "genome": genome,
           "fingerprint_vector": fingerprint, "system_prompt": spec}
    _save("genome", agg)
    return agg


def render_spec(slug: str, genome: dict, cards: dict) -> str:
    """把基因组渲染成一段 system-prompt——另一个 LLM 读了就能按该风格写。"""
    L = []
    L.append(f"# 文风复现规格(STYLE GENOME · 源自《{slug}》)")
    L.append("你要严格模仿以下作者的文风与写作架构来创作。这是一套可执行的范式,请逐条遵循。\n")
    sm = (cards.get("style") or {}) if False else None  # style summary 可选
    lex = genome.get("lexicon") or {}
    if lex.get("categories"):
        L.append("## 用词范式")
        L.append(f"总体用词:{lex.get('diction','')}。回避:{lex.get('avoid','')}")
        for c in lex["categories"][:8]:
            words = "、".join((c.get("signature_words") or [])[:10])
            L.append(f"- 【{c.get('name')}】常用:{words};例:{' / '.join((c.get('example_phrases') or [])[:2])}")
    syn = genome.get("syntax") or {}
    if syn.get("sentence_patterns"):
        L.append("\n## 句式范式")
        L.append(f"节奏:{syn.get('rhythm','')};分段:{syn.get('paragraphing','')};标点:{syn.get('punctuation','')}")
        for p in syn["sentence_patterns"][:6]:
            L.append(f"- 句式「{p.get('pattern')}」用于{p.get('function','')};例:{(p.get('examples') or [''])[0]}")
    rhe = genome.get("rhetoric") or {}
    if rhe.get("devices"):
        L.append("\n## 修辞范式")
        L.append(f"招牌:{rhe.get('signature_move','')};意象取材:{'、'.join(rhe.get('imagery_sources') or [])}")
        for d in rhe["devices"][:6]:
            L.append(f"- {d.get('device')}:{d.get('tendency','')}")
    atm = genome.get("atmosphere") or {}
    if atm.get("genres"):
        L.append("\n## 类型氛围配方")
        for g in atm["genres"][:4]:
            L.append(f"### {g.get('genre')}")
            for m in (g.get("mechanisms") or [])[:6]:
                L.append(f"- {m.get('means')}:{m.get('how','')}")
        if atm.get("golden_rules"):
            L.append("准则:" + ";".join(atm["golden_rules"][:6]))
    sr = genome.get("scene_routine") or {}
    if sr.get("routines"):
        L.append("\n## 场景套路(写某类场面的固定打法)")
        for r in sr["routines"][:10]:
            L.append(f"### {r.get('scene_type')}")
            L.append(f"- 切入:{r.get('opening_move','')};视角:{r.get('pov_angle','')}")
            seq = r.get("beat_sequence") or []
            if seq:
                L.append(f"- 节拍序列:{' → '.join(map(str, seq))}")
            L.append(f"- 详略:{r.get('detail_distribution','')};收尾:{r.get('ending_hook','')}")
    ma = genome.get("macro_arch") or {}
    if ma.get("templates"):
        t = ma["templates"]
        L.append("\n## 宏观编排架构")
        L.append(f"幕结构:{t.get('act_structure','')}")
        L.append(f"阶段模板:{t.get('stage_template','')}")
        L.append(f"伏笔策略:{t.get('foreshadow_strategy','')}")
        L.append(f"升级逻辑:{t.get('escalation_logic','')}")
        if t.get("reusable_skeleton"):
            L.append("可套用骨架:" + " → ".join(map(str, t["reusable_skeleton"][:10])))
        met = ma.get("metrics", {}).get("tension_modulation", {})
        if met:
            L.append(f"张力:均{met.get('avg')}、约每{met.get('climax_interval')}章一个大高潮。")
    tr = genome.get("transition") or {}
    if tr.get("most_likely_next"):
        L.append("\n## 场景递进倾向(上一拍→最可能的下一拍)")
        L.append("；".join(f"{a}→{b}" for a, b in list(tr["most_likely_next"].items())[:8]))
    L.append("\n## 硬性输出约束")
    L.append("- 直接写正文,不要输出章节标题、小标题、Markdown(如 # / ## / 第X幕)、作者注或任何元信息。")
    L.append("- 严格按场景类型路由对应的用词密度/句式/调度,避免全程一个腔;弱断言(似乎/仿佛)勿超原作频率。")
    return "\n".join(L)


def get_genome(slug: str) -> dict:
    with book_scope(slug):
        init_schema()
        with session_scope() as s:
            cards = {c.category: c.card_json for c in s.execute(select(M.AnalysisCard)).scalars().all()}
        genome = {ly: cards.get(f"genome.{ly}") for ly in LAYERS}
        agg = cards.get("genome") or {}
        return {"slug": slug, "genome": genome, "system_prompt": agg.get("system_prompt"),
                "fingerprint_vector": agg.get("fingerprint_vector"),
                "layers_present": [ly for ly in LAYERS if cards.get(f"genome.{ly}")]}
