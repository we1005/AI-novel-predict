"""pytest 引导:把墨笔 backend 与墨析 backend 加入 sys.path。
(红蓝对抗 E7:全仓此前零自动化测试——这是第一个回归套件,锁住已修复的确定性逻辑。)"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
for p in (os.path.join(ROOT, "backend"),
          os.path.join(ROOT, "novel-analysis-imitate", "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

# CI 安全网:settings.json 已 gitignore,CI 上缺失会让依赖 config 的模块导入失败。
# 缺失时补一个最小 stub(本地有真文件则不动)。
_data = os.path.join(ROOT, "backend", "data")
_settings = os.path.join(_data, "settings.json")
if not os.path.exists(_settings):
    import json
    os.makedirs(_data, exist_ok=True)
    json.dump({
        "default_model_fast": "stub", "default_model_strong": "stub", "base_url": "",
        "providers": {p: {"api_key": "", "base_url": ""} for p in ("dashscope", "volc", "xiaomi")},
    }, open(_settings, "w"))
