#!/usr/bin/env bash
# 复用现有 backend 的 .venv(依赖完全一致)+ 把本服务加入 PYTHONPATH。
# 现有 app 的 DATA_DIR=../../backend/data,故成员书与 settings 与续写项目共享。
cd "$(dirname "$0")"
PYTHONPATH=. ../../backend/.venv/bin/python -m uvicorn naimitate.main:app --host 0.0.0.0 --port 8100
