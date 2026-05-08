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

from ..config import DATA_DIR, MODEL_FAST, MODEL_STRONG

# ---------------------------------------------------------------------------
# Static catalogues
# ---------------------------------------------------------------------------

# 已知模型（用户可在这里之外手动输入任意模型名）。
# 价格是 USD per million tokens；不在表中的也能用，只是 cost 列显示 0。
KNOWN_MODELS: list[dict[str, Any]] = [
    # ── 思考 / 顶配 ──
    {"id": "qwen3-max-preview", "label": "Qwen3-Max-Preview",
     "tier": "max", "tag": "深度思考", "price_in": 0.83, "price_out": 3.33,
     "desc": "极强思考能力，最长上下文"},
    {"id": "qwen-max",          "label": "Qwen-Max",
     "tier": "max", "tag": "稳定旗舰", "price_in": 0.33, "price_out": 1.33,
     "desc": "稳定的旗舰创作模型"},

    # ── 平衡 ──
    {"id": "qwen-plus",         "label": "Qwen-Plus",
     "tier": "plus", "tag": "性价比", "price_in": 0.11, "price_out": 0.28,
     "desc": "性价比之选；中等创意任务"},

    # ── Flash 系列（默认） ──
    {"id": "qwen3.5-flash",     "label": "Qwen3.5-Flash",
     "tier": "flash", "tag": "默认", "price_in": 0.04, "price_out": 0.42,
     "desc": "默认抽取/决策模型；快且便宜"},
    {"id": "qwen-flash",        "label": "Qwen-Flash",
     "tier": "flash", "tag": "快速", "price_in": 0.04, "price_out": 0.42,
     "desc": "更轻量的 Flash 版本"},

    # ── 用户截图里看到的较新候选（如未来开放可填入） ──
    {"id": "qwen3.6-flash",     "label": "Qwen3.6-Flash",
     "tier": "flash", "tag": "新", "price_in": 0.04, "price_out": 0.42,
     "desc": "更高效率，更低成本"},
    {"id": "qwen3.6-plus",      "label": "Qwen3.6-Plus",
     "tier": "plus", "tag": "深度思考", "price_in": 0.11, "price_out": 0.28,
     "desc": "更低成本更强思考"},
    {"id": "qwen3.6-max-preview", "label": "Qwen3.6-Max-Preview",
     "tier": "max", "tag": "Coding+", "price_in": 0.83, "price_out": 3.33,
     "desc": "Coding 与 Agent 执行能力提升"},
    {"id": "deepseek-v4-flash", "label": "DeepSeek-V4-Flash",
     "tier": "flash", "tag": "外部", "price_in": 0.05, "price_out": 0.50,
     "desc": "DeepSeek 的轻量快速版"},
    {"id": "deepseek-v4-pro",   "label": "DeepSeek-V4-Pro",
     "tier": "max", "tag": "外部", "price_in": 0.40, "price_out": 1.50,
     "desc": "性能比肩顶级闭源模型"},
]


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


def _empty_settings() -> dict[str, Any]:
    return {
        "default_model_fast": MODEL_FAST,
        "default_model_strong": MODEL_STRONG,
        # API credentials (override what's in backend/.env). Empty string → use env.
        "api_key": "",
        "base_url": "",
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


def get_settings() -> dict[str, Any]:
    cur = _settings_cached()
    # Don't leak the full API key over the wire — return a masked version
    # plus enough metadata for the UI to know whether one is configured.
    from ..config import OPENAI_API_KEY as ENV_KEY, OPENAI_BASE_URL as ENV_URL
    safe_settings = dict(cur)
    safe_settings["api_key"] = _mask_key(cur.get("api_key") or "")
    safe_settings["api_key_set"] = bool(cur.get("api_key"))
    safe_settings["api_key_source"] = (
        "settings" if cur.get("api_key") else ("env" if ENV_KEY else "none")
    )
    safe_settings["base_url"] = cur.get("base_url") or ""
    safe_settings["effective_base_url"] = cur.get("base_url") or ENV_URL

    return {
        "settings": safe_settings,
        "agents": list_agents(),
        "models": list_models(),
        "lanes": [
            {"id": LANE_FAST, "label": "FAST",
             "current": cur["default_model_fast"]},
            {"id": LANE_STRONG, "label": "STRONG",
             "current": cur["default_model_strong"]},
        ],
    }


def get_credentials() -> tuple[str, str]:
    """Return (api_key, base_url) for the OpenAI client. Settings override env."""
    from ..config import OPENAI_API_KEY as ENV_KEY, OPENAI_BASE_URL as ENV_URL
    cur = _settings_cached()
    return (cur.get("api_key") or ENV_KEY, cur.get("base_url") or ENV_URL)


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

        if "api_key" in payload and isinstance(payload["api_key"], str):
            new_key = payload["api_key"].strip()
            # Treat the masked placeholder ("****...****") as "no change".
            looks_masked = new_key and set(new_key) <= set("*") | set(new_key[:4]) | set(new_key[-4:]) and "*" in new_key
            if not looks_masked and new_key != cur.get("api_key"):
                cur["api_key"] = new_key
                creds_changed = True
        if "base_url" in payload and isinstance(payload["base_url"], str):
            new_url = payload["base_url"].strip()
            if new_url != cur.get("base_url"):
                cur["base_url"] = new_url
                creds_changed = True

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
