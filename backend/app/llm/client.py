"""OpenAI-compatible client wrapper (used against Aliyun DashScope's Qwen).

Centralizes:
  * a single chokepoint that all extraction / prediction code calls through
  * OpenAI tool-calling for structured JSON output
  * per-call audit (tokens / latency / $) into ``llm_calls``

Why a single chokepoint: every other module — extraction agents, prediction
pipeline, future editor — should call through here so the monitor dashboard
sees a complete picture without scattered instrumentation.

Note on prompt caching: the Anthropic SDK had per-block ``cache_control``;
DashScope's OpenAI-compatible endpoint exposes no equivalent today, so the
``cache_*`` columns in ``llm_calls`` will simply stay zero. We keep the columns
to avoid a schema migration if/when Aliyun adds prefix caching.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from ..config import (
    MODEL_FAST,
    MODEL_STRONG,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    PRICE_PER_MTOK,
)
from ..db import session_scope
from ..memory.models import LLMCall
from ..settings.store import apply_overrides, credentials_version, get_credentials

_client: OpenAI | None = None
_client_version: int = -1


def get_client() -> OpenAI:
    """Return a process-cached OpenAI client. Recreates if settings.json
    overrode the API key / base URL since the last call."""
    global _client, _client_version
    cur_version = credentials_version()
    if _client is None or _client_version != cur_version:
        api_key, base_url = get_credentials()
        if not api_key:
            raise RuntimeError(
                "API key not set — configure DASHSCOPE_API_KEY in backend/.env "
                "or set one in /settings"
            )
        _client = OpenAI(api_key=api_key, base_url=base_url or OPENAI_BASE_URL)
        _client_version = cur_version
    return _client


def cached_block(text: str) -> str:
    """No-op compatibility shim.

    Anthropic's ``cache_control`` blocks let large stable context (entity
    table, world rules, foreshadow list) sit in a 5-minute prompt cache.
    DashScope's OpenAI-compatible endpoint has no equivalent yet, so this
    just returns the text — the call sites still concatenate stable parts
    first so a future caching layer can drop in unchanged.
    """

    return text


def estimate_cost_usd(model: str, usage: dict[str, int]) -> float:
    p = PRICE_PER_MTOK.get(model)
    if p is None:
        return 0.0
    inp = usage.get("input_tokens", 0) / 1e6 * p["input"]
    out = usage.get("output_tokens", 0) / 1e6 * p["output"]
    return round(inp + out, 6)


@dataclass
class LLMResponse:
    text: str
    tool_use: dict[str, Any] | None
    raw: Any
    usage: dict[str, int]
    cost_usd: float
    elapsed_ms: int


def _to_openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Convert our internal tool schema (Anthropic-flavored: ``name``,
    ``description``, ``input_schema``) into OpenAI's ``function`` form."""

    if "function" in tool:
        return tool  # already in OpenAI form
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema") or tool.get("parameters", {}),
        },
    }


def _record(session: Session, *, agent: str, model: str, usage: dict[str, int],
            elapsed_ms: int, cost: float, extra: dict[str, Any] | None = None) -> None:
    session.add(
        LLMCall(
            agent=agent,
            model=model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_creation_tokens=0,
            cache_read_tokens=0,
            elapsed_ms=elapsed_ms,
            cost_usd=cost,
            extra_json=extra or {},
        )
    )


def _normalize_messages(system: Any, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """OpenAI uses a flat messages list with role=system entries.

    The rest of this codebase carries ``system`` either as a string or as
    a list of `{type:"text", text:...}` blocks (legacy from when this code
    targeted the Anthropic SDK). Flatten both into one OpenAI ``system``
    message, then prepend.
    """

    if isinstance(system, str):
        sys_text = system
    elif isinstance(system, list):
        sys_text = "\n\n".join(
            (b.get("text", "") if isinstance(b, dict) else str(b)) for b in system
        )
    else:
        sys_text = str(system)

    out: list[dict[str, Any]] = []
    if sys_text.strip():
        out.append({"role": "system", "content": sys_text})

    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            content = "\n".join(
                (b.get("text", "") if isinstance(b, dict) else str(b)) for b in content
            )
        out.append({"role": m.get("role", "user"), "content": content})
    return out


@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=2, max=20), reraise=True)
def call(
    *,
    agent: str,
    model: str,
    system: str | list[dict[str, Any]],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: dict[str, Any] | str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    top_p: float | None = None,
    extra_log: dict[str, Any] | None = None,
) -> LLMResponse:
    client = get_client()
    model, temperature, max_tokens, top_p = apply_overrides(
        agent, model=model, temperature=temperature, max_tokens=max_tokens, top_p=top_p,
    )
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": _normalize_messages(system, messages),
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if top_p is not None:
        kwargs["top_p"] = top_p
    if tools:
        kwargs["tools"] = [_to_openai_tool(t) for t in tools]
        if tool_choice is not None:
            if isinstance(tool_choice, dict) and tool_choice.get("type") == "tool":
                kwargs["tool_choice"] = {
                    "type": "function",
                    "function": {"name": tool_choice["name"]},
                }
            else:
                kwargs["tool_choice"] = tool_choice
            # Qwen3.x models default to thinking mode, which rejects forced
            # tool_choice. Disable it whenever we're forcing a specific tool.
            kwargs["extra_body"] = {"enable_thinking": False}

    t0 = time.perf_counter()
    resp = client.chat.completions.create(**kwargs)
    elapsed = int((time.perf_counter() - t0) * 1000)

    usage_obj = getattr(resp, "usage", None)
    usage = {
        "input_tokens": getattr(usage_obj, "prompt_tokens", 0) or 0,
        "output_tokens": getattr(usage_obj, "completion_tokens", 0) or 0,
    }
    cost = estimate_cost_usd(model, usage)

    msg = resp.choices[0].message if resp.choices else None
    text = (msg.content or "") if msg else ""
    tool_use: dict[str, Any] | None = None
    if msg and getattr(msg, "tool_calls", None):
        first = msg.tool_calls[0]
        try:
            args = json.loads(first.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {"_raw": first.function.arguments}
        tool_use = {"name": first.function.name, "input": args}

    with session_scope() as s:
        _record(s, agent=agent, model=model, usage=usage, elapsed_ms=elapsed, cost=cost,
                extra=extra_log)

    return LLMResponse(
        text=text,
        tool_use=tool_use,
        raw=resp,
        usage=usage,
        cost_usd=cost,
        elapsed_ms=elapsed,
    )


def stream_text(
    *,
    agent: str,
    model: str,
    system: str | list[dict[str, Any]],
    messages: list[dict[str, Any]],
    max_tokens: int = 4096,
    temperature: float = 0.7,
    top_p: float | None = None,
):
    """Yield text chunks; after the stream finishes, record one ``llm_calls``
    row with the final usage block. Caller iterates this generator and writes
    chunks to the HTTP response.
    """

    client = get_client()
    model, temperature, max_tokens, top_p = apply_overrides(
        agent, model=model, temperature=temperature, max_tokens=max_tokens, top_p=top_p,
    )
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": _normalize_messages(system, messages),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if top_p is not None:
        kwargs["top_p"] = top_p

    t0 = time.perf_counter()
    usage = {"input_tokens": 0, "output_tokens": 0}
    chunks_yielded = 0
    for chunk in client.chat.completions.create(**kwargs):
        if chunk.usage is not None:
            usage = {
                "input_tokens": getattr(chunk.usage, "prompt_tokens", 0) or 0,
                "output_tokens": getattr(chunk.usage, "completion_tokens", 0) or 0,
            }
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        text = getattr(delta, "content", None)
        if text:
            chunks_yielded += 1
            yield text
    elapsed = int((time.perf_counter() - t0) * 1000)

    cost = estimate_cost_usd(model, usage)
    with session_scope() as s:
        _record(
            s,
            agent=agent,
            model=model,
            usage=usage,
            elapsed_ms=elapsed,
            cost=cost,
            extra={"streamed": True, "chunks": chunks_yielded},
        )


def stable_json(obj: Any) -> str:
    """Serialize JSON deterministically.

    Mostly inherited from the Anthropic-era cache-stability rule; still useful
    here because (a) it makes prompts diff-friendly and (b) we want the same
    bytes if Aliyun ships prefix caching later.
    """

    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


__all__ = [
    "call",
    "cached_block",
    "estimate_cost_usd",
    "get_client",
    "LLMResponse",
    "stable_json",
    "stream_text",
    "MODEL_FAST",
    "MODEL_STRONG",
]
