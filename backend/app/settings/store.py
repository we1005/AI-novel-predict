"""Runtime-tunable settings: per-agent model + sampling overrides.

We keep two layers:

1. **Code defaults** — hardcoded in ``AGENT_REGISTRY`` below. These mirror the
   actual values each pipeline passes to ``llm.call`` / ``llm.stream_text``.
   Source of truth; do not silently drift.
2. **User overrides** — persisted to ``data/settings.json``. Schema:

       {
         "default_model_fast":   "qwen3.5-flash",
         "default_model_strong": "qwen3.5-flash",
         "agents": {
           "predict.diverge": {
             "model": null | "qwen-max",
             "temperature": null | 0.7,
             "max_tokens": null | 8000,
             "top_p": null | 0.9
           },
           ...
         }
       }

   ``null`` means "fall back to code default".
"""

from __future__ import annotations

import json
import threading
from typing import Any

from ..config import (
    DATA_DIR,
    DEFAULT_PROVIDER,
    MODEL_FAST,
    MODEL_STRONG,
    PROVIDERS,
)

# ---------------------------------------------------------------------------
# Static catalogues
# ---------------------------------------------------------------------------

# 已知模型（用户可在这里之外手动输入任意模型名）。
# 价格是 USD per million tokens；不在表中的也能用，只是 cost 列显示 0。
# ``provider`` 决定走哪个 base_url + api_key（见 config.PROVIDERS）。
KNOWN_MODELS: list[dict[str, Any]] = [
    # ═══════════════ 阿里 DashScope (Qwen) ═══════════════
    # ── 思考 / 顶配 ──
    {"id": "qwen3-max-preview", "label": "Qwen3-Max-Preview", "provider": "dashscope",
     "tier": "max", "tag": "深度思考", "price_in": 0.83, "price_out": 3.33,
     "desc": "极强思考能力，最长上下文"},
    {"id": "qwen-max",          "label": "Qwen-Max", "provider": "dashscope",
     "tier": "max", "tag": "稳定旗舰", "price_in": 0.33, "price_out": 1.33,
     "desc": "稳定的旗舰创作模型"},

    # ── 平衡 ──
    {"id": "qwen-plus",         "label": "Qwen-Plus", "provider": "dashscope",
     "tier": "plus", "tag": "性价比", "price_in": 0.11, "price_out": 0.28,
     "desc": "性价比之选；中等创意任务"},

    # ── Flash 系列（默认） ──
    {"id": "qwen3.5-flash",     "label": "Qwen3.5-Flash", "provider": "dashscope",
     "tier": "flash", "tag": "默认", "price_in": 0.04, "price_out": 0.42,
     "desc": "默认抽取/决策模型；快且便宜"},
    {"id": "qwen-flash",        "label": "Qwen-Flash", "provider": "dashscope",
     "tier": "flash", "tag": "快速", "price_in": 0.04, "price_out": 0.42,
     "desc": "更轻量的 Flash 版本"},

    # ── 用户截图里看到的较新候选（如未来开放可填入） ──
    {"id": "qwen3.6-flash",     "label": "Qwen3.6-Flash", "provider": "dashscope",
     "tier": "flash", "tag": "新", "price_in": 0.04, "price_out": 0.42,
     "desc": "更高效率，更低成本"},
    {"id": "qwen3.6-plus",      "label": "Qwen3.6-Plus", "provider": "dashscope",
     "tier": "plus", "tag": "深度思考", "price_in": 0.11, "price_out": 0.28,
     "desc": "更低成本更强思考"},
    {"id": "qwen3.6-max-preview", "label": "Qwen3.6-Max-Preview", "provider": "dashscope",
     "tier": "max", "tag": "Coding+", "price_in": 0.83, "price_out": 3.33,
     "desc": "Coding 与 Agent 执行能力提升"},

    # ═══════════════ 火山引擎 Coding-Plan (豆包 / Kimi / GLM / MiniMax) ═══════════════
    # 走 config.PROVIDERS["volc"] —— 价格并入 coding-plan 订阅，故 cost 列显示 0。
    # ── Coding 旗舰 / 顶配 ──
    {"id": "doubao-seed-2.0-code", "label": "Doubao-Seed-2.0-Code", "provider": "volc",
     "tier": "max", "tag": "Coding旗舰", "price_in": 0.0, "price_out": 0.0,
     "desc": "豆包 2.0 代码旗舰，最强 Coding/Agent"},
    {"id": "doubao-seed-2.0-pro", "label": "Doubao-Seed-2.0-Pro", "provider": "volc",
     "tier": "max", "tag": "通用旗舰", "price_in": 0.0, "price_out": 0.0,
     "desc": "豆包 2.0 通用旗舰，强推理与长文"},
    {"id": "minimax-m3", "label": "MiniMax-M3", "provider": "volc",
     "tier": "max", "tag": "旗舰", "price_in": 0.0, "price_out": 0.0,
     "desc": "MiniMax M3 旗舰模型"},
    {"id": "glm-5.2", "label": "GLM-5.2 (glm-latest)", "provider": "volc",
     "tier": "max", "tag": "旗舰", "price_in": 0.0, "price_out": 0.0,
     "desc": "智谱 GLM-5.2，指向 glm-latest"},
    {"id": "deepseek-v4-pro", "label": "DeepSeek-V4-Pro", "provider": "volc",
     "tier": "max", "tag": "旗舰", "price_in": 0.0, "price_out": 0.0,
     "desc": "DeepSeek V4 Pro，性能比肩顶级闭源"},

    # ── 平衡 / Coding ──
    {"id": "doubao-seed-code", "label": "Doubao-Seed-Code", "provider": "volc",
     "tier": "plus", "tag": "Coding", "price_in": 0.0, "price_out": 0.0,
     "desc": "豆包代码模型（上一代）"},
    {"id": "minimax-m2.7", "label": "MiniMax-M2.7", "provider": "volc",
     "tier": "plus", "tag": "性价比", "price_in": 0.0, "price_out": 0.0,
     "desc": "MiniMax M2.7 平衡模型"},
    {"id": "kimi-k2.6", "label": "Kimi-K2.6", "provider": "volc",
     "tier": "plus", "tag": "长文", "price_in": 0.0, "price_out": 0.0,
     "desc": "月之暗面 Kimi K2.6"},

    # ── 轻量 / 快速 ──
    {"id": "doubao-seed-2.0-lite", "label": "Doubao-Seed-2.0-Lite", "provider": "volc",
     "tier": "flash", "tag": "快速", "price_in": 0.0, "price_out": 0.0,
     "desc": "豆包 2.0 轻量版，快且便宜"},
    {"id": "deepseek-v4-flash", "label": "DeepSeek-V4-Flash", "provider": "volc",
     "tier": "flash", "tag": "快速", "price_in": 0.0, "price_out": 0.0,
     "desc": "DeepSeek V4 轻量快速版"},

    # ── 小米 MiMo(OpenAI 兼容;额度充裕;支持 response_format=json_object,无 json_schema strict)──
    {"id": "mimo-v2.5-pro", "label": "MiMo-v2.5-Pro", "provider": "xiaomi",
     "tier": "max", "tag": "强推理", "price_in": 0.0, "price_out": 0.0,
     "desc": "小米 MiMo 2.5 Pro：1M 上下文/128K 输出,复杂推理/长文"},
    {"id": "mimo-v2-pro", "label": "MiMo-v2-Pro", "provider": "xiaomi",
     "tier": "max", "tag": "强推理", "price_in": 0.0, "price_out": 0.0, "desc": "小米 MiMo 2 Pro"},
    {"id": "mimo-v2.5", "label": "MiMo-v2.5 (Omni)", "provider": "xiaomi",
     "tier": "plus", "tag": "全模态", "price_in": 0.0, "price_out": 0.0, "desc": "小米 MiMo 2.5 全模态"},
    {"id": "mimo-v2-omni", "label": "MiMo-v2-Omni", "provider": "xiaomi",
     "tier": "plus", "tag": "全模态", "price_in": 0.0, "price_out": 0.0, "desc": "小米 MiMo 2 全模态"},
    {"id": "mimo-v2-flash", "label": "MiMo-v2-Flash", "provider": "xiaomi",
     "tier": "flash", "tag": "快速", "price_in": 0.0, "price_out": 0.0,
     "desc": "小米 MiMo 2 Flash：256K 上下文,低成本快速响应"},
]

# model id → provider id（路由 base_url + api_key 用）。
_MODEL_PROVIDER: dict[str, str] = {m["id"]: m.get("provider", DEFAULT_PROVIDER)
                                   for m in KNOWN_MODELS}


def provider_for_model(model_id: str) -> str:
    """Which provider a model id belongs to. Unknown ids → default provider
    (keeps hand-typed Qwen model names working)."""
    return _MODEL_PROVIDER.get(model_id, DEFAULT_PROVIDER)


# Tier shorthand → 默认归属哪条 lane（用作"重置成默认"的依据）。
LANE_FAST = "fast"
LANE_STRONG = "strong"


# 全部 agent 的代码默认值。新增 agent 时在这里同步。
# (model 字段写 LANE_FAST / LANE_STRONG 表示走 default_model_*。)
AGENT_REGISTRY: list[dict[str, Any]] = [
    # ── 抽取 ──
    {"id": "extract.entity",     "group": "抽取", "lane": LANE_FAST,
     "temperature": 0.3, "max_tokens": 4000, "top_p": None,
     "desc": "实体抽取（人/物/势/法/概念）"},
    {"id": "extract.foreshadow", "group": "抽取", "lane": LANE_FAST,
     "temperature": 0.3, "max_tokens": 4000, "top_p": None,
     "desc": "伏笔追踪（planted / resolved）"},
    {"id": "extract.state",      "group": "抽取", "lane": LANE_FAST,
     "temperature": 0.3, "max_tokens": 4000, "top_p": None,
     "desc": "关键人物状态变化"},
    {"id": "extract.plot",       "group": "抽取", "lane": LANE_FAST,
     "temperature": 0.3, "max_tokens": 4000, "top_p": None,
     "desc": "重要剧情节点"},
    {"id": "extract.world",      "group": "抽取", "lane": LANE_FAST,
     "temperature": 0.3, "max_tokens": 4000, "top_p": None,
     "desc": "世界设定术语"},
    {"id": "extract.mystery",    "group": "抽取", "lane": LANE_FAST,
     "temperature": 0.3, "max_tokens": 4000, "top_p": None,
     "desc": "读者未解疑点（跨批增量）"},
    {"id": "relationships.extract", "group": "抽取", "lane": LANE_FAST,
     "temperature": 0.3, "max_tokens": 4000, "top_p": None,
     "desc": "实体关系抽取"},

    # ── 预测 ──
    {"id": "predict.diverge",    "group": "预测", "lane": LANE_STRONG,
     "temperature": 0.95, "max_tokens": 8000, "top_p": 0.95,
     "desc": "Stage A：发散 N 条候选剧情"},
    {"id": "predict.score",      "group": "预测", "lane": LANE_STRONG,
     "temperature": 0.2, "max_tokens": 4000, "top_p": None,
     "desc": "Stage B：评分并选出 winner"},
    {"id": "predict.write",      "group": "预测", "lane": LANE_STRONG,
     "temperature": 0.75, "max_tokens": 8000, "top_p": None,
     "desc": "Stage C：流式写正文"},
    {"id": "arc.diverge",        "group": "预测", "lane": LANE_STRONG,
     "temperature": 0.9, "max_tokens": 12000, "top_p": None,
     "desc": "全弧 Stage A：100+ 章主线发散"},
    {"id": "arc.score",          "group": "预测", "lane": LANE_STRONG,
     "temperature": 0.2, "max_tokens": 4000, "top_p": None,
     "desc": "全弧 Stage B：主线评分"},

    # ── 写作 ──
    {"id": "outline.refine",     "group": "写作", "lane": LANE_STRONG,
     "temperature": 0.6, "max_tokens": 10000, "top_p": None,
     "desc": "phase 拆成逐章大纲"},
    {"id": "draft.writer",       "group": "写作", "lane": LANE_STRONG,
     "temperature": 0.75, "max_tokens": 8000, "top_p": None,
     "desc": "章节正文 Writer"},
    {"id": "draft.review.style", "group": "写作", "lane": LANE_FAST,
     "temperature": 0.2, "max_tokens": 4000, "top_p": None,
     "desc": "文风审查"},
    {"id": "draft.review.plot",  "group": "写作", "lane": LANE_FAST,
     "temperature": 0.2, "max_tokens": 4000, "top_p": None,
     "desc": "剧情审查"},
    {"id": "draft.review.consistency", "group": "写作", "lane": LANE_FAST,
     "temperature": 0.2, "max_tokens": 4000, "top_p": None,
     "desc": "一致性审查"},
    {"id": "draft.editor",       "group": "写作", "lane": LANE_FAST,
     "temperature": 0.2, "max_tokens": 4000, "top_p": None,
     "desc": "Editor 仲裁"},

    # ── 文笔风格 ──
    {"id": "style.analyze",      "group": "文笔", "lane": LANE_STRONG,
     "temperature": 0.3, "max_tokens": 8000, "top_p": None,
     "desc": "作者文风分析（抽样章节 → 结构化风格画像）"},
    {"id": "translate.zh2en",    "group": "文笔", "lane": LANE_STRONG,
     "temperature": 0.4, "max_tokens": 8000, "top_p": None,
     "desc": "中→英 翻译（双语续写用）"},
    {"id": "translate.en2zh",    "group": "文笔", "lane": LANE_STRONG,
     "temperature": 0.4, "max_tokens": 8000, "top_p": None,
     "desc": "英→中 翻译（双语续写用）"},
    {"id": "bilingual.merge",    "group": "文笔", "lane": LANE_STRONG,
     "temperature": 0.6, "max_tokens": 32000, "top_p": None,
     "desc": "双语取长补短融合，产出最终中英版本（reasoning 长度不稳，留足 max_tokens + 长度兜底）"},
    {"id": "bilingual.en_writer", "group": "文笔", "lane": LANE_STRONG,
     "temperature": 0.8, "max_tokens": 8000, "top_p": None,
     "desc": "英文母语独立成稿（双语续写用，走 minimax-m3 散文道）"},
    {"id": "revoice.skeleton",   "group": "文笔", "lane": LANE_STRONG,
     "temperature": 0.2, "max_tokens": 4000, "top_p": None,
     "desc": "重写文笔：抽剧情骨架（结构化 JSON → doubao-code）"},
    {"id": "revoice.write.wangwen", "group": "文笔", "lane": LANE_STRONG,
     "temperature": 0.75, "max_tokens": 8000, "top_p": None,
     "desc": "重写文笔：网文腔重写"},
    {"id": "revoice.write.mimic", "group": "文笔", "lane": LANE_STRONG,
     "temperature": 0.75, "max_tokens": 8000, "top_p": None,
     "desc": "重写文笔：仿原作者笔法重写"},
    {"id": "revoice.write.en",   "group": "文笔", "lane": LANE_STRONG,
     "temperature": 0.75, "max_tokens": 8000, "top_p": None,
     "desc": "重写文笔：英文母语重写"},

    # ── 笔法片段库（09）──
    {"id": "craft.tag",          "group": "文笔", "lane": LANE_FAST,
     "temperature": 0.3, "max_tokens": 6000, "top_p": None,
     "desc": "笔法片段分类打标（逐批扫全书，高频便宜调用，适合 deepseek-v4-flash 等廉价模型）"},
    {"id": "craft.card",         "group": "文笔", "lane": LANE_STRONG,
     "temperature": 0.3, "max_tokens": 4000, "top_p": None,
     "desc": "逐类笔法风格拆解（基于片段产风格卡）"},

    # ── 仿真 ──
    {"id": "profile.build",      "group": "仿真", "lane": LANE_FAST,
     "temperature": 0.3, "max_tokens": 4000, "top_p": None,
     "desc": "角色档案构建"},
    {"id": "interview",          "group": "仿真", "lane": LANE_FAST,
     "temperature": 0.7, "max_tokens": 2000, "top_p": None,
     "desc": "角色第一人称问答（流式）"},
    {"id": "sim.decide",         "group": "仿真", "lane": LANE_FAST,
     "temperature": 0.85, "max_tokens": 2000, "top_p": 0.95,
     "desc": "DecisionAgent：每轮每角色决策"},
    {"id": "sim.report",         "group": "仿真", "lane": LANE_STRONG,
     "temperature": 0.7, "max_tokens": 8000, "top_p": None,
     "desc": "ReportAgent：综合成章"},
]


_AGENT_BY_ID: dict[str, dict[str, Any]] = {a["id"]: a for a in AGENT_REGISTRY}


# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------

_SETTINGS_PATH = DATA_DIR / "settings.json"
_LOCK = threading.Lock()


def _empty_providers() -> dict[str, dict[str, str]]:
    # Per-provider credential overrides. Empty string → fall back to env
    # (config.PROVIDERS[...]). Keyed by provider id.
    return {pid: {"api_key": "", "base_url": ""} for pid in PROVIDERS}


def _empty_settings() -> dict[str, Any]:
    return {
        "default_model_fast": MODEL_FAST,
        "default_model_strong": MODEL_STRONG,
        # Legacy single-credential fields — map to the DEFAULT_PROVIDER
        # (dashscope). Kept for backward compat; new per-provider creds live
        # under "providers". Empty string → use env.
        "api_key": "",
        "base_url": "",
        "providers": _empty_providers(),
        "agents": {a["id"]: {"model": None, "temperature": None,
                             "max_tokens": None, "top_p": None}
                   for a in AGENT_REGISTRY},
    }


def _load_raw() -> dict[str, Any]:
    if not _SETTINGS_PATH.exists():
        return _empty_settings()
    try:
        with _SETTINGS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _empty_settings()

    # Backfill: if registry grew, add missing agents.
    base = _empty_settings()
    base["default_model_fast"] = data.get("default_model_fast") or MODEL_FAST
    base["default_model_strong"] = data.get("default_model_strong") or MODEL_STRONG
    base["api_key"] = data.get("api_key") or ""
    base["base_url"] = data.get("base_url") or ""

    # Per-provider creds. Backfill any provider missing from an older file, and
    # migrate the legacy top-level api_key/base_url onto the default provider so
    # an existing single-credential config keeps working after the upgrade.
    saved_providers = data.get("providers") or {}
    for pid in base["providers"]:
        sp = saved_providers.get(pid) or {}
        base["providers"][pid] = {
            "api_key": sp.get("api_key") or "",
            "base_url": sp.get("base_url") or "",
        }
    dp = base["providers"].get(DEFAULT_PROVIDER)
    if dp is not None:
        if not dp["api_key"] and base["api_key"]:
            dp["api_key"] = base["api_key"]
        if not dp["base_url"] and base["base_url"]:
            dp["base_url"] = base["base_url"]

    saved_agents = data.get("agents") or {}
    for aid in base["agents"]:
        if aid in saved_agents:
            base["agents"][aid] = {
                "model":       saved_agents[aid].get("model"),
                "temperature": saved_agents[aid].get("temperature"),
                "max_tokens":  saved_agents[aid].get("max_tokens"),
                "top_p":       saved_agents[aid].get("top_p"),
            }
    return base


def _save_raw(data: dict[str, Any]) -> None:
    with _SETTINGS_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# In-memory cache (reload on save).
_CACHE: dict[str, Any] | None = None

# Bumped any time credentials change — llm.client uses this to invalidate its
# cached OpenAI() instance.
_CREDS_VERSION: int = 0


def credentials_version() -> int:
    return _CREDS_VERSION


def _settings_cached() -> dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _load_raw()
    return _CACHE


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_models() -> list[dict[str, Any]]:
    return list(KNOWN_MODELS)


def list_agents() -> list[dict[str, Any]]:
    """Return the registry with current overrides merged in."""

    cur = _settings_cached()
    out: list[dict[str, Any]] = []
    for a in AGENT_REGISTRY:
        ov = cur["agents"].get(a["id"], {})
        default_model = (
            cur["default_model_strong"] if a["lane"] == LANE_STRONG
            else cur["default_model_fast"]
        )
        out.append({
            "id": a["id"],
            "group": a["group"],
            "lane": a["lane"],
            "desc": a["desc"],
            "defaults": {
                "model": default_model,
                "temperature": a["temperature"],
                "max_tokens": a["max_tokens"],
                "top_p": a["top_p"],
            },
            "overrides": {
                "model":       ov.get("model"),
                "temperature": ov.get("temperature"),
                "max_tokens":  ov.get("max_tokens"),
                "top_p":       ov.get("top_p"),
            },
        })
    return out


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def _provider_override(cur: dict[str, Any], pid: str) -> dict[str, str]:
    return (cur.get("providers") or {}).get(pid) or {"api_key": "", "base_url": ""}


def resolve_provider_creds(pid: str, cur: dict[str, Any] | None = None) -> tuple[str, str]:
    """(api_key, base_url) for a provider. settings.json override → env default."""
    if cur is None:
        cur = _settings_cached()
    meta = PROVIDERS.get(pid, PROVIDERS[DEFAULT_PROVIDER])
    ov = _provider_override(cur, pid)
    api_key = ov.get("api_key") or meta.get("api_key") or ""
    base_url = ov.get("base_url") or meta.get("base_url") or ""
    return api_key, base_url


def list_providers() -> list[dict[str, Any]]:
    """Per-provider metadata for the settings UI (keys masked, never raw)."""
    cur = _settings_cached()
    out: list[dict[str, Any]] = []
    for pid, meta in PROVIDERS.items():
        ov = _provider_override(cur, pid)
        ov_key = ov.get("api_key") or ""
        env_key = meta.get("api_key") or ""
        eff_key, eff_url = resolve_provider_creds(pid, cur)
        out.append({
            "id": pid,
            "label": meta.get("label", pid),
            "env_var": meta.get("env_key", ""),
            "default_base_url": meta.get("base_url", ""),
            "api_key": _mask_key(ov_key),          # masked override (if any)
            "api_key_set": bool(eff_key),
            "api_key_source": ("settings" if ov_key else ("env" if env_key else "none")),
            "base_url": ov.get("base_url") or "",   # raw override (non-secret)
            "effective_base_url": eff_url,
        })
    return out


def get_settings() -> dict[str, Any]:
    cur = _settings_cached()
    # Don't leak the full API key over the wire — return a masked version
    # plus enough metadata for the UI to know whether one is configured.
    # Legacy top-level api_key/base_url mirror the DEFAULT_PROVIDER so the old
    # single-provider UI keeps rendering even before it's upgraded.
    safe_settings = dict(cur)
    def_key, def_url = resolve_provider_creds(DEFAULT_PROVIDER, cur)
    def_ov = _provider_override(cur, DEFAULT_PROVIDER)
    safe_settings["api_key"] = _mask_key(def_ov.get("api_key") or "")
    safe_settings["api_key_set"] = bool(def_key)
    safe_settings["api_key_source"] = (
        "settings" if def_ov.get("api_key") else
        ("env" if PROVIDERS[DEFAULT_PROVIDER].get("api_key") else "none")
    )
    safe_settings["base_url"] = def_ov.get("base_url") or ""
    safe_settings["effective_base_url"] = def_url
    safe_settings["extract_max_tokens"] = get_extract_max_tokens()
    # Mask any per-provider keys carried in the raw settings dict.
    safe_settings["providers"] = {
        pid: {"api_key": _mask_key((v or {}).get("api_key") or ""),
              "base_url": (v or {}).get("base_url") or ""}
        for pid, v in (cur.get("providers") or {}).items()
    }

    return {
        "settings": safe_settings,
        "agents": list_agents(),
        "models": list_models(),
        "providers": list_providers(),
        "lanes": [
            {"id": LANE_FAST, "label": "FAST",
             "current": cur["default_model_fast"]},
            {"id": LANE_STRONG, "label": "STRONG",
             "current": cur["default_model_strong"]},
        ],
    }


def get_extract_max_tokens(default: int = 8000) -> int:
    """抽取 agent 的输出 token 上限(设置页可配)。长章/超长章可调高以免漏抽。"""
    try:
        v = int(_settings_cached().get("extract_max_tokens") or default)
        return max(2000, min(32000, v))
    except (TypeError, ValueError):
        return default


def get_credentials(model_id: str | None = None) -> tuple[str, str]:
    """Return (api_key, base_url) for the OpenAI client.

    With a ``model_id``, routes to that model's provider. Without one, falls
    back to the default provider (backward-compatible behaviour).
    """
    cur = _settings_cached()
    pid = provider_for_model(model_id) if model_id else DEFAULT_PROVIDER
    return resolve_provider_creds(pid, cur)


def update_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Patch known fields. Unknown keys ignored. Returns full settings."""

    global _CACHE, _CREDS_VERSION
    creds_changed = False
    with _LOCK:
        cur = _load_raw()

        if "default_model_fast" in payload and isinstance(payload["default_model_fast"], str):
            cur["default_model_fast"] = payload["default_model_fast"].strip() or MODEL_FAST
        if "default_model_strong" in payload and isinstance(payload["default_model_strong"], str):
            cur["default_model_strong"] = payload["default_model_strong"].strip() or MODEL_STRONG

        if "extract_max_tokens" in payload:
            try:
                cur["extract_max_tokens"] = max(2000, min(32000, int(payload["extract_max_tokens"])))
            except (TypeError, ValueError):
                pass

        def _is_masked(v: str) -> bool:
            # Treat the masked placeholder ("****...****") as "no change".
            return bool(v) and set(v) <= set("*") | set(v[:4]) | set(v[-4:]) and "*" in v

        cur.setdefault("providers", _empty_providers())
        for pid in PROVIDERS:
            cur["providers"].setdefault(pid, {"api_key": "", "base_url": ""})

        # Legacy single-credential fields → route onto the default provider.
        if "api_key" in payload and isinstance(payload["api_key"], str):
            new_key = payload["api_key"].strip()
            row = cur["providers"][DEFAULT_PROVIDER]
            if not _is_masked(new_key) and new_key != row.get("api_key"):
                row["api_key"] = new_key
                cur["api_key"] = new_key
                creds_changed = True
        if "base_url" in payload and isinstance(payload["base_url"], str):
            new_url = payload["base_url"].strip()
            row = cur["providers"][DEFAULT_PROVIDER]
            if new_url != row.get("base_url"):
                row["base_url"] = new_url
                cur["base_url"] = new_url
                creds_changed = True

        # Per-provider credential overrides.
        prov = payload.get("providers") or {}
        for pid, ov in prov.items():
            if pid not in cur["providers"] or not isinstance(ov, dict):
                continue
            row = cur["providers"][pid]
            if "api_key" in ov and isinstance(ov["api_key"], str):
                nk = ov["api_key"].strip()
                if not _is_masked(nk) and nk != row.get("api_key"):
                    row["api_key"] = nk
                    creds_changed = True
                    if pid == DEFAULT_PROVIDER:
                        cur["api_key"] = nk
            if "base_url" in ov and isinstance(ov["base_url"], str):
                nu = ov["base_url"].strip()
                if nu != row.get("base_url"):
                    row["base_url"] = nu
                    creds_changed = True
                    if pid == DEFAULT_PROVIDER:
                        cur["base_url"] = nu

        ag = payload.get("agents") or {}
        for aid, ov in ag.items():
            if aid not in cur["agents"] or not isinstance(ov, dict):
                continue
            row = cur["agents"][aid]
            if "model" in ov:
                v = ov["model"]
                row["model"] = (v.strip() or None) if isinstance(v, str) else None
            if "temperature" in ov:
                v = ov["temperature"]
                row["temperature"] = float(v) if isinstance(v, (int, float)) else None
            if "max_tokens" in ov:
                v = ov["max_tokens"]
                row["max_tokens"] = int(v) if isinstance(v, (int, float)) else None
            if "top_p" in ov:
                v = ov["top_p"]
                row["top_p"] = float(v) if isinstance(v, (int, float)) else None

        _save_raw(cur)
        _CACHE = cur
        if creds_changed:
            _CREDS_VERSION += 1
    return get_settings()


def reset_settings() -> dict[str, Any]:
    global _CACHE, _CREDS_VERSION
    with _LOCK:
        cur = _empty_settings()
        _save_raw(cur)
        _CACHE = cur
        _CREDS_VERSION += 1
    return get_settings()


# ---------------------------------------------------------------------------
# Hot-path: applied at every llm.call / llm.stream_text
# ---------------------------------------------------------------------------


def get_agent_default(agent: str) -> dict[str, Any] | None:
    return _AGENT_BY_ID.get(agent)


def apply_overrides(
    agent: str,
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    top_p: float | None,
) -> tuple[str, float, int, float | None]:
    """Apply user overrides for this agent. Returns the final tuple to pass to
    the OpenAI client. If no overrides are set, returns inputs verbatim.

    Cheap lookup — only one dict get per call. Loads settings.json once and
    keeps it in process memory.
    """

    cur = _settings_cached()
    ov = cur["agents"].get(agent) or {}

    if ov.get("model"):
        final_model = ov["model"]
    else:
        # Resolve lane default. Agents not in the registry fall back to whatever
        # the caller passed in (treat unknown as "no override").
        meta = _AGENT_BY_ID.get(agent)
        if meta is None:
            final_model = model
        elif meta["lane"] == LANE_STRONG:
            final_model = cur.get("default_model_strong") or model
        else:
            final_model = cur.get("default_model_fast") or model

    final_temp = ov["temperature"] if ov.get("temperature") is not None else temperature
    final_max = ov["max_tokens"] if ov.get("max_tokens") is not None else max_tokens
    final_top_p = ov["top_p"] if ov.get("top_p") is not None else top_p
    return final_model, float(final_temp), int(final_max), final_top_p
