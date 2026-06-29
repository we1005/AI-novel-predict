# -*- coding: utf-8 -*-
"""红蓝对抗修复的回归测试(E7:此前全仓零测试)。
锁住:D3 arc winner 维度、E1 抽取空解析可见性、结构维指纹判别(E1/数字之争)。
均为确定性、无需 DB/网络。"""
import pytest


# ---- D3:_ensure_arc_winner 必须按 arc 真实 5 维综合分选,而非旧维度名导致的"纯新颖度" ----
def test_arc_winner_uses_real_dimensions():
    from app.predict.arc import _ensure_arc_winner
    score = {"scores": [
        {"index": 0, "macro_coherence": 95, "evidence_quality": 95,
         "foreshadow_coverage": 80, "hero_arc": 80, "novelty": 10},
        {"index": 1, "macro_coherence": 20, "evidence_quality": 20,
         "foreshadow_coverage": 20, "hero_arc": 20, "novelty": 90},
    ]}
    out = _ensure_arc_winner(score, 2)
    # 候选0 综合更稳健;旧 bug(只 novelty 重合)会错选候选1
    assert out["winner_index"] == 0


def test_arc_winner_respects_valid_index():
    from app.predict.arc import _ensure_arc_winner
    assert _ensure_arc_winner({"winner_index": 1, "scores": []}, 3)["winner_index"] == 1


# ---- E1:_extract_loads_json 对垃圾/截断返回 {}(记录其有损行为;run_batch 据此告警)----
def test_extract_loads_json_valid():
    from app.ingest.extract import _extract_loads_json
    assert _extract_loads_json('{"entities": [{"name": "张三"}]}')["entities"][0]["name"] == "张三"


def test_extract_loads_json_strips_fences():
    from app.ingest.extract import _extract_loads_json
    assert _extract_loads_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_loads_json_unrepairable_returns_empty():
    from app.ingest.extract import _extract_loads_json
    # 完全无法修复 → {}(run_batch 的 `not out` 告警能抓到这一类)
    assert _extract_loads_json("not json at all") == {}
    assert _extract_loads_json("") == {}


def test_extract_loads_json_truncated_is_fabricated_not_empty():
    # E1 的更隐蔽变体(测试发现):截断 JSON 会被 json_repair "修"成
    # 结构合法但内容空的对象(如 {entities:[{name:''}]}),它**非空**,
    # 会绕过 run_batch 的 `not out` 告警。故 E1 完整修复需"内容级"校验而非仅判空。
    from app.ingest.extract import _extract_loads_json
    out = _extract_loads_json('{"entities": [{"name": ')
    assert out  # 非空(被 json_repair 编造),而非干净的 {}


# ---- 结构维指纹:与基因组无关、判别力强(E1/数字之争 的客观尺子)----
def test_structural_features_shape():
    from naimitate.analysis import _fingerprint as FP
    f = FP.structural_features("他走进房间。“你来了。”她说。这是一个很长的句子用来测试。")
    assert set(f) >= {"avg_sent_len", "sent_len_cv", "para_len_mean",
                      "dialogue_ratio", "comma_per_kchar"}
    assert 0.0 <= f["dialogue_ratio"] <= 1.0
    assert f["avg_sent_len"] > 0


def test_fingerprint_compare_same_beats_cross():
    from naimitate.analysis import _fingerprint as FP
    # 长句、少对白的"克苏鲁腔"
    src = ("黑暗在墙壁的纹理间缓缓蠕动,仿佛某种不可名状之物正于砖石深处呼吸,"
           "而他只能僵立原地,任由那股黏腻的寒意顺着脊椎一寸寸爬升,直至意识的边缘开始崩解。") * 6
    same = ("潮湿的气息自地窖深处弥漫上来,仿佛亘古的低语在砖缝里盘绕不去,"
            "他屏住呼吸,感到某种无法名状的存在正缓慢地靠近,理智如薄冰般寸寸开裂。") * 6
    # 短句、多对白、多叹号的"网文腔"
    cross = ("“住手!”他大喝。\n“凭什么?”\n少年冷笑。\n他出手了!\n快!太快了!\n众人惊呼。\n") * 12
    s = FP.fingerprint_from_text(src)
    fid_same = FP.compare(s, FP.fingerprint_from_text(same))["fidelity_score"]
    fid_cross = FP.compare(s, FP.fingerprint_from_text(cross))["fidelity_score"]
    assert fid_same is not None and fid_cross is not None
    assert fid_same > fid_cross  # 同腔保真度应高于跨腔


# ---- E8:EntityState items 状态/diff 对账(reconcile_items) ----
def test_reconcile_items_gain():
    from app.ingest.extract import reconcile_items
    items, net = reconcile_items(["剑"], ["盾", "弓"], [])
    assert items == ["剑", "弓", "盾"] and set(net) == {"盾", "弓"}


def test_reconcile_items_gain_and_lose_same_change_cancels():
    # 同章既得又失 → 净为无,state 不含,net_gained 不计(diff 与 state 一致可逆)
    from app.ingest.extract import reconcile_items
    items, net = reconcile_items(["剑"], ["金灵根"], ["金灵根"])
    assert "金灵根" not in items and net == [] and items == ["剑"]


def test_reconcile_items_lose_existing():
    from app.ingest.extract import reconcile_items
    items, net = reconcile_items(["剑", "盾"], [], ["盾"])
    assert items == ["剑"] and net == []


# ---- E6:跨 provider 降级 wrapper(默认关闭;配了才降级) ----
def test_e6_no_fallback_reraises(monkeypatch):
    from app.llm import client
    monkeypatch.setattr(client, "get_fallback_model", lambda default="": "")
    def boom(**kw):
        raise RuntimeError("429 rate limit")
    monkeypatch.setattr(client, "_call_impl", boom)
    import pytest
    with pytest.raises(RuntimeError):
        client.call(agent="t", model="m1", system="s", messages=[{"role": "user", "content": "x"}])


def test_e6_failover_to_fallback(monkeypatch):
    from app.llm import client
    monkeypatch.setattr(client, "get_fallback_model", lambda default="": "fallback-m2")
    calls = []
    def impl(**kw):
        calls.append(kw["model"])
        if kw["model"] == "m1":
            raise RuntimeError("429 rate limit")
        return "OK-FROM-FALLBACK"
    monkeypatch.setattr(client, "_call_impl", impl)
    out = client.call(agent="t", model="m1", system="s", messages=[{"role": "user", "content": "x"}])
    assert out == "OK-FROM-FALLBACK" and calls == ["m1", "fallback-m2"]


# ---- E4:仿真每轮活状态(非冻结)+ 产物落 draft 的纯函数 ----
def test_e4_fold_round_accumulates_per_character_trail():
    from app.sim.simulator import _fold_round_into_state
    cs = {"张三": {"state": {}}, "李四": {"state": {}}}
    _fold_round_into_state(cs, [
        {"character": "张三", "kind": "speak", "content": "我去查档案"},
        {"character": "李四", "kind": "move", "content": "尾随张三"},
    ], 1)
    _fold_round_into_state(cs, [
        {"character": "张三", "kind": "act", "content": "撬开抽屉"},
    ], 2)
    # 张三轨迹累积两轮、李四一轮 → 下一轮各自 my_current_state 带演进(非冻结初始)
    assert [e["round"] for e in cs["张三"]["events_during_sim"]] == [1, 2]
    assert cs["张三"]["events_during_sim"][1]["kind"] == "act"
    assert len(cs["李四"]["events_during_sim"]) == 1


def test_e4_fold_round_ignores_anonymous_and_handles_nondict_slot():
    from app.sim.simulator import _fold_round_into_state
    cs = {"王五": "原是字符串而非dict"}  # 非 dict slot 也要稳健
    _fold_round_into_state(cs, [
        {"kind": "speak", "content": "无名氏"},      # 无 character → 跳过
        {"character": "王五", "kind": "speak", "content": "嗯"},
    ], 1)
    assert isinstance(cs["王五"], dict) and len(cs["王五"]["events_during_sim"]) == 1


def test_e4_chapter_title_from_text():
    from app.sim.simulator import _chapter_title_from_text
    assert _chapter_title_from_text("第 158 章 归途\n\n正文……", 157) == "第 158 章 归途"
    # 空正文 → 默认标题(after_chapter+1)
    assert _chapter_title_from_text("   \n  ", 157) == "第 158 章"


# ---- E2:向量层启用开关(默认关 + 跨重启留存)+ 状态辅助安全降级 ----
def test_e2_vector_flag_default_off_and_persists(tmp_path, monkeypatch):
    from app.settings import store
    monkeypatch.setattr(store, "_SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(store, "_CACHE", None)
    try:
        assert store.get_vector_recall_enabled() is False          # 默认关闭
        store.update_settings({"vector_recall_enabled": True})
        store._CACHE = None                                        # 模拟进程重启:从盘重载
        assert store.get_vector_recall_enabled() is True           # _load_raw 必须保留该标量
    finally:
        store._CACHE = None


def test_e2_vector_helpers_safe_and_lazy():
    from app.memory import vector as v
    assert isinstance(v.deps_available(), bool)
    assert v.model_loaded() is False                # 启动/未用时模型不加载(惰性)
    assert isinstance(v.indexed_count(), int)       # 缺依赖/空库也返回 int,不抛
    st = v.reindex_state()
    assert st["status"] in ("idle", "running", "done", "failed")


# ---- #78:话题 push 增强 开关(默认开 + 跨重启留存)+ 盲评位置去偏映射 ----
def test_e78_topic_push_default_on_and_persists(tmp_path, monkeypatch):
    from app.settings import store
    monkeypatch.setattr(store, "_SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(store, "_CACHE", None)
    try:
        assert store.get_topic_push_enabled() is True          # 默认开启(PUSH 默认)
        store.update_settings({"topic_push_enabled": False})
        store._CACHE = None                                    # 模拟重启:从盘重载
        assert store.get_topic_push_enabled() is False         # 关闭状态必须留存
    finally:
        store._CACHE = None


def test_e78_ab_winner_position_debias_mapping():
    from app.draft.pipeline import _map_ab_winner
    # swap=False:甲=off, 乙=on
    assert _map_ab_winner("甲", False) == "off"
    assert _map_ab_winner("乙", False) == "on"
    # swap=True:甲=on, 乙=off(位置交换后映射必须翻转)
    assert _map_ab_winner("甲", True) == "on"
    assert _map_ab_winner("乙", True) == "off"
    # 平/未知
    assert _map_ab_winner("平", False) == "平/未知"


# ---- #79:agentic 检索 opt-in 开关(默认关 + 跨重启留存)+ 任意标签盲评映射 ----
def test_e79_agentic_default_off_and_persists(tmp_path, monkeypatch):
    from app.settings import store
    monkeypatch.setattr(store, "_SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(store, "_CACHE", None)
    try:
        assert store.get_agentic_search_enabled() is False     # 默认关(opt-in)
        store.update_settings({"agentic_search_enabled": True})
        store._CACHE = None                                    # 模拟重启:从盘重载
        assert store.get_agentic_search_enabled() is True
    finally:
        store._CACHE = None


def test_e79_ab_winner_custom_labels():
    from app.draft.pipeline import _map_ab_winner
    # push 臂=prose_a(label_a), agentic 臂=prose_b(label_b)
    assert _map_ab_winner("甲", False, "push", "agentic") == "push"
    assert _map_ab_winner("乙", False, "push", "agentic") == "agentic"
    assert _map_ab_winner("甲", True, "push", "agentic") == "agentic"   # swap 翻转
    assert _map_ab_winner("乙", True, "push", "agentic") == "push"


def test_genre_template_render_system_prompt():
    # genre_template 渲染:纯函数,组装语义部件 + 内建求异/负面清单护栏(V2)
    from naimitate.generate.genre_template import render_system_prompt
    sp = render_system_prompt({
        "imagery": ["雾都", "煤气灯", "蒸汽机械"],
        "motifs": ["禁忌知识致疯"],
        "worldview_lexicon": ["非凡者", "值夜者"],
        "atmosphere": "压抑疏离、知识即诅咒",
        "flavor_recipe": "在煤气灯下研究深渊的冰冷考究口吻",
        "anti_patterns": ["嘴角勾起", "空气仿佛凝固"],
    })
    assert "雾都" in sp and "煤气灯" in sp                       # 意象进了
    assert "值夜者" in sp                                         # 世界观语汇进了
    assert "写作护栏" in sp and "嘴角勾起" in sp                  # V2 求异 + 负面清单进了
    # 关掉护栏则不含求异段
    sp2 = render_system_prompt({"imagery": ["雾都"]}, anti_cliche=False)
    assert "写作护栏" not in sp2


def test_genre_template_render_empty_safe():
    from naimitate.generate.genre_template import render_system_prompt
    sp = render_system_prompt({})                                # 空模板也不崩,仍给默认护栏
    assert "类型写作配方" in sp and "写作护栏" in sp


def test_genre_template_knobs_graded():
    # V6 旋钮分档:类型强度/求异度 0-100 → 渲染出可区分的低/中/高档措辞(纯函数)
    from naimitate.generate.genre_template import render_system_prompt, _band
    assert (_band(10), _band(50), _band(90)) == (0, 1, 2)
    t = {"imagery": ["雾都"], "anti_patterns": ["嘴角勾起"]}
    low_g = render_system_prompt(t, genre_strength=10, novelty=60)
    hi_g = render_system_prompt(t, genre_strength=90, novelty=60)
    assert "轻触" in low_g and "浓墨重彩" in hi_g                  # 强度档位可区分
    # 求异=0 → 无护栏;求异高 → 大胆求异
    assert "写作护栏" not in render_system_prompt(t, genre_strength=70, novelty=0)
    assert "求异=大胆" in render_system_prompt(t, genre_strength=70, novelty=90)
    assert "求异=稳妥" in render_system_prompt(t, genre_strength=70, novelty=10)


def test_syntax_cliche_hit_density():
    # 句法层:套路句式同句共现命中(确定性,无通配)
    from naimitate.analysis._fingerprint import cliche_hit_density, syntax_metrics
    cliche = "他的瞳孔骤然收缩。反派冷笑一声。少年眼底寒芒一闪。" * 3   # 多套路
    clean = "雨落在青石板上,远处传来钟声,他慢慢走过空荡的长街。" * 3   # 无套路
    assert cliche_hit_density(cliche) > cliche_hit_density(clean)
    assert cliche_hit_density(clean) == 0.0
    m = syntax_metrics("他被一种不可名状的恐惧攫住,以至于无法动弹。")
    assert m["western_connector_per_kchar"] > 0 and m["abstract_passive_per_kchar"] > 0


def test_genre_template_syntax_layer_render():
    # 句法层渲染:题材句式(受类型强度)+ 套路句式负面清单(受求异度,大胆档=硬禁用)
    from naimitate.generate.genre_template import render_system_prompt
    t = {"imagery": ["雾都"],
         "syntactic_patterns": ["状语前置营造译本腔 — 在那扇门后,蛰伏着……"],
         "cliche_sentence_templates": ["<人物>的<眼>寒芒一闪", "<反派>冷笑一声"]}
    # inject_syntax 默认 False(V_syntax 实测注入反更套路)→ 默认不渲句法层
    assert "题材句式" not in render_system_prompt(t, genre_strength=90, novelty=60)
    assert "句式负面清单" not in render_system_prompt(t, genre_strength=70, novelty=90)
    # 显式 inject_syntax=True(实验用)才渲:类型强度高→题材句式,轻触→不渲
    assert "题材句式" in render_system_prompt(t, genre_strength=90, novelty=60, inject_syntax=True)
    assert "题材句式" not in render_system_prompt(t, genre_strength=10, novelty=60, inject_syntax=True)
    hi = render_system_prompt(t, genre_strength=70, novelty=90, inject_syntax=True)
    assert "句式负面清单·硬禁用" in hi and "寒芒一闪" in hi
    assert "句式负面清单" not in render_system_prompt(t, genre_strength=70, novelty=0, inject_syntax=True)


def test_e79_ab_judge_forwards_labels(monkeypatch):
    # 集成防回归:_ab_judge 必须把 label_a/label_b **传进** _map_ab_winner
    # (曾漏传 → agentic A/B 误显示 on/off)。monkeypatch 掉 llm + random 使其确定。
    import random as _r

    from app.draft import pipeline
    from app.llm import client as _llm

    monkeypatch.setattr(_r, "random", lambda: 0.9)          # swap=False → 甲=prose_a
    class _Resp:
        text = '{"winner":"甲","reason":"x"}'
        cost_usd = 0.0
    monkeypatch.setattr(_llm, "call", lambda **k: _Resp())
    v, _ = pipeline._ab_judge({"intent": "i"}, "A", "B", 1, label_a="push", label_b="agentic")
    assert v["winner_variant"] == "push"   # 修复前会错成 "off"
