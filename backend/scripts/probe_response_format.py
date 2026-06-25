"""探测火山(volc)各模型对 response_format 两种模式的支持情况。

直连 provider client(绕过 llm.call 的自动降级),以便区分"支持 / API报错 / 解析失败 / 不合规"。
两种模式:
  - json_object:{"type":"json_object"}
  - json_schema(strict):{"type":"json_schema","json_schema":{...,"strict":true}}
schema 只用火山 strict 支持的关键字(type/properties/required/additionalProperties/items/enum),
不含 minItems/minimum 等不支持项。
"""

from __future__ import annotations

import json
import time

from app.llm.client import get_client
from app.settings.store import KNOWN_MODELS

VOLC = [m["id"] for m in KNOWN_MODELS if m.get("provider") == "volc"]

PROMPT = ("请以 JSON 输出一本书的信息:title(书名,字符串)、score(0-100 的整数)、"
          "tags(字符串数组)、mood(只能是 happy 或 sad)。书:一部关于草原与战争的史诗。")

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "score": {"type": "integer"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "mood": {"type": "string", "enum": ["happy", "sad"]},
    },
    "required": ["title", "score", "tags", "mood"],
    "additionalProperties": False,
}


def _conforms(d: dict) -> bool:
    return (isinstance(d, dict)
            and isinstance(d.get("title"), str)
            and isinstance(d.get("score"), int)
            and isinstance(d.get("tags"), list)
            and d.get("mood") in ("happy", "sad"))


def _probe(model: str, rf: dict, check_schema: bool) -> str:
    client = get_client(model)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PROMPT}],
            max_tokens=600,
            temperature=0.2,
            response_format=rf,
        )
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        short = msg[:90].replace("\n", " ")
        return f"❌ API报错: {short}"
    txt = (resp.choices[0].message.content or "") if resp.choices else ""
    if "```" in txt:
        return "⚠ 有围栏```(未强制纯JSON)"
    try:
        d = json.loads(txt)
    except Exception:
        return f"⚠ 非合法JSON(需repair) 前40:{txt[:40]!r}"
    if check_schema:
        return "✅ 合法JSON+合规结构" if _conforms(d) else "⚠ 合法JSON但不合schema"
    return "✅ 合法JSON"


def main() -> None:
    print(f"探测 {len(VOLC)} 个火山模型 × 2 模式\n", flush=True)
    rows = []
    for m in VOLC:
        t0 = time.time()
        jo = _probe(m, {"type": "json_object"}, check_schema=False)
        t1 = time.time()
        js = _probe(m, {"type": "json_schema",
                        "json_schema": {"name": "book", "strict": True, "schema": SCHEMA}},
                    check_schema=True)
        t2 = time.time()
        rows.append((m, jo, js))
        print(f"[{m}]\n   json_object : {jo}  ({t1-t0:.0f}s)\n   json_schema : {js}  ({t2-t1:.0f}s)", flush=True)
    print("\n==== 汇总表 ====", flush=True)
    print(f"{'模型':<24} | {'json_object':<22} | json_schema(strict)", flush=True)
    for m, jo, js in rows:
        print(f"{m:<24} | {jo:<22} | {js}", flush=True)
    print("PROBE_DONE", flush=True)


if __name__ == "__main__":
    main()
