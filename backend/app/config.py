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
}

BATCH_SIZE_CHAPTERS = 50
DEFAULT_CANDIDATES = 5
EMBEDDING_MODEL = "BAAI/bge-large-zh-v1.5"
