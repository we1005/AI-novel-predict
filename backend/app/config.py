from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
# Load backend/.env so DASHSCOPE_API_KEY etc. don't have to be exported each shell.
# Real env vars still win — we only fill in what's missing.
load_dotenv(BACKEND_DIR / ".env", override=False)

DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# DB / chroma / corpus paths are now per-book — see books/library.py.
# Use ``books.library.active_paths()`` to resolve the current book's paths.

# Qwen via Aliyun DashScope's OpenAI-compatible endpoint.
# Both env vars work; DASHSCOPE_API_KEY takes precedence so user-supplied
# DashScope keys aren't accidentally shadowed by an unrelated OPENAI_API_KEY.
OPENAI_API_KEY = (
    os.environ.get("DASHSCOPE_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or ""
)
OPENAI_BASE_URL = os.environ.get(
    "OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# 火山引擎 (字节豆包) Coding-Plan OpenAI-compatible endpoint.
ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
ARK_BASE_URL = os.environ.get(
    "ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding/v3"
)

# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------
# Each provider is an OpenAI-compatible endpoint with its own base_url + api_key.
# A model declares which provider it belongs to (see settings.store.KNOWN_MODELS),
# and llm.client routes the request to that provider's credentials. The env
# values below are the *defaults* — settings.json can override per-provider creds.
#
# ``DEFAULT_PROVIDER`` is the one the legacy single-credential settings
# (top-level ``api_key`` / ``base_url``) and ``MODEL_FAST`` / ``MODEL_STRONG``
# defaults map to, so existing deployments keep working untouched.
DEFAULT_PROVIDER = "dashscope"

PROVIDERS: dict[str, dict[str, str]] = {
    "dashscope": {
        "label": "阿里 DashScope (Qwen / DeepSeek)",
        "base_url": OPENAI_BASE_URL,
        "api_key": OPENAI_API_KEY,
        "env_key": "DASHSCOPE_API_KEY",
    },
    "volc": {
        "label": "火山引擎 Coding-Plan (豆包 / Kimi / GLM / MiniMax)",
        "base_url": ARK_BASE_URL,
        "api_key": ARK_API_KEY,
        "env_key": "ARK_API_KEY",
    },
}

# Default to qwen3.5-flash for both fast (extraction) and strong (prediction +
# prose) lanes. Override per-lane via env vars (e.g. MODEL_STRONG=qwen3-max for
# higher-quality creative writing once you've verified the extraction loop).
MODEL_FAST = os.environ.get("MODEL_FAST", "qwen3.5-flash")
MODEL_STRONG = os.environ.get("MODEL_STRONG", "qwen3.5-flash")

# USD per million tokens. Aliyun publishes RMB pricing; conversion is rough
# (¥7.2 ≈ $1). Anything not listed falls back to 0 (cost column shows 0).
PRICE_PER_MTOK = {
    "qwen3.5-flash": {"input": 0.04, "output": 0.42},
    "qwen-flash": {"input": 0.04, "output": 0.42},
    "qwen-plus": {"input": 0.11, "output": 0.28},
    "qwen-max": {"input": 0.33, "output": 1.33},
    "qwen3-max-preview": {"input": 0.83, "output": 3.33},
    # 火山引擎 Coding-Plan — pricing is bundled into the coding-plan subscription,
    # so per-token cost is left at 0 (the monitor cost column shows 0 for these).
    "doubao-seed-2.0-code": {"input": 0.0, "output": 0.0},
    "doubao-seed-2.0-pro": {"input": 0.0, "output": 0.0},
    "doubao-seed-2.0-lite": {"input": 0.0, "output": 0.0},
    "doubao-seed-code": {"input": 0.0, "output": 0.0},
    "minimax-m2.7": {"input": 0.0, "output": 0.0},
    "minimax-m3": {"input": 0.0, "output": 0.0},
    "glm-5.2": {"input": 0.0, "output": 0.0},
    "deepseek-v4-flash": {"input": 0.0, "output": 0.0},
    "deepseek-v4-pro": {"input": 0.0, "output": 0.0},
    "kimi-k2.6": {"input": 0.0, "output": 0.0},
}

BATCH_SIZE_CHAPTERS = 50
DEFAULT_CANDIDATES = 5
EMBEDDING_MODEL = "BAAI/bge-large-zh-v1.5"
