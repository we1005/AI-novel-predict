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
