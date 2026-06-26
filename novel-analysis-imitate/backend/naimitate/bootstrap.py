"""让新服务能 import 现有续写项目的 `app` 包(复用 LLM/抽取/风格/笔法/生成内核)。

不复制代码:把同仓库的 ../../backend 加入 sys.path,直接 `from app.xxx import ...`。
现有 app 的 DATA_DIR = backend/data,故 per-book 数据与 settings 天然共享现有书库。
"""
from __future__ import annotations
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3] / "backend"  # visible-AI-novel-writer/backend


def ensure_app_importable() -> Path:
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    return _BACKEND
