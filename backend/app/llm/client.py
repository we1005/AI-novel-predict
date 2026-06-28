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

# 限流类错误(账号级频率限制)需要远比"瞬时抖动"更长的退避——20s 窗口内根本不会解除。
_RATE_LIMIT_MARKERS = ("429", "ratelimit", "rate limit", "toomanyrequests",
                       "accountratelimitexceeded", "too frequent", "requests are too")


def _is_rate_limit(exc: BaseException | None) -> bool:
    return bool(exc) and any(m in str(exc).lower() for m in _RATE_LIMIT_MARKERS)


def _adaptive_wait(retry_state):
    """限流错误:长退避(initial 15s, max 120s);其它瞬时错误:短退避(2s/max20s)。"""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if _is_rate_limit(exc):
        return wait_exponential_jitter(initial=15, max=120)(retry_state)
    return wait_exponential_jitter(initial=2, max=20)(retry_state)


def _adaptive_stop(retry_state):
    """限流错误:最多 7 次(熬过频率窗口);其它错误:3 次即止。
    修复 E6:若配了 fallback_model(跨 provider 降级),限流只重试 2 次就快速失败,交给 call() 降级到
    备用 provider,不再 7×(15~120s)死等 ~14 分钟。未配降级则维持 7 次(原行为)。"""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if _is_rate_limit(exc):
        try:
            limit = 2 if get_fallback_model() else 7
        except Exception:
            limit = 7
    else:
        limit = 3
    return retry_state.attempt_number >= limit

from ..config import (
    DEFAULT_PROVIDER,
    MODEL_FAST,
    MODEL_STRONG,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    PRICE_PER_MTOK,
    PROVIDERS,
)
from ..db import session_scope
from ..memory.models import LLMCall
from ..settings.store import (
    apply_overrides,
    credentials_version,
    get_credentials,
    get_fallback_model,
    provider_for_model,
)

# One cached OpenAI() per provider id. Invalidated whenever credentials_version()
# bumps (i.e. settings.json creds changed).
_clients: dict[str, OpenAI] = {}
_client_version: int = -1


def get_client(model: str | None = None) -> OpenAI:
    """Return a process-cached OpenAI client for ``model``'s provider.

    Routes by the model's provider so a single request always uses the right
    base_url + api_key. Recreates clients if settings.json overrode credentials
    since the last call. ``model=None`` resolves the default provider.
    """
    global _clients, _client_version
    cur_version = credentials_version()
    if _client_version != cur_version:
        _clients = {}                      # creds changed → drop all cached clients
        _client_version = cur_version

    pid = provider_for_model(model) if model else DEFAULT_PROVIDER
    client = _clients.get(pid)
    if client is None:
        api_key, base_url = get_credentials(model)
        if not api_key:
            env_var = PROVIDERS.get(pid, {}).get("env_key", "DASHSCOPE_API_KEY")
            raise RuntimeError(
                f"API key not set for provider '{pid}' — configure {env_var} in "
                f"backend/.env or set one in /settings"
            )
        client = OpenAI(api_key=api_key, base_url=base_url or OPENAI_BASE_URL)
        _clients[pid] = client
    return client


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


# 支持 json_schema strict(连结构都保证)的模型白名单(实测:火山 doubao-seed-2.0-pro/lite)。
RESPONSE_FORMAT_MODELS = {"doubao-seed-2.0-pro", "doubao-seed-2.0-lite"}
# 仅支持 json_object(只保证合法 JSON、不强结构)的模型:小米 MiMo 全系。
# 传入 json_schema 时对这些模型**降级**为 json_object(见下)。
JSON_OBJECT_ONLY_MODELS = {"mimo-v2.5-pro", "mimo-v2-pro", "mimo-v2.5",
                           "mimo-v2-omni"}


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


@retry(stop=_adaptive_stop, wait=_adaptive_wait, reraise=True)
def _call_impl(
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
    response_format: str | dict[str, Any] | None = None,
    extra_log: dict[str, Any] | None = None,
) -> LLMResponse:
    model, temperature, max_tokens, top_p = apply_overrides(
        agent, model=model, temperature=temperature, max_tokens=max_tokens, top_p=top_p,
    )
    # Route to the right provider (base_url + api_key) based on the resolved model.
    client = get_client(model)
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
            # tool_choice. Disable it whenever we're forcing a specific tool —
            # but only on DashScope; the param is non-standard and other
            # providers (e.g. 火山引擎) would reject the unknown body field.
            if provider_for_model(model) == "dashscope":
                kwargs["extra_body"] = {"enable_thinking": False}

    # 结构化输出:只对**实测确认支持**的模型挂 response_format(消除 ```围栏/markdown/
    # 散文前言;json_schema 还保证结构)。实测火山仅 doubao-seed-2.0-pro/lite 真支持两种
    # 模式;其余 400 拒绝或吐空(见 docs/火山引擎-结构化输出-response_format.md)。
    # 不在白名单的模型不挂(走 JSON-in-text + json_repair)。仍保留下面的兜底回退。
    if response_format and model in RESPONSE_FORMAT_MODELS:
        rf = {"type": "json_object"} if isinstance(response_format, str) else response_format
        kwargs["response_format"] = rf
    elif response_format and model in JSON_OBJECT_ONLY_MODELS:
        # 小米只支持 json_object:无论传 json_object 还是 json_schema,统一降级为 json_object
        # (结构靠提示词里贴的 schema 引导 + json_repair 兜底)。
        kwargs["response_format"] = {"type": "json_object"}
    # 小米 MiMo 默认禁用深度思考(thinking 经 extra_body;我们的结构化/抽取任务不需推理,
    # 且开思考会吞输出预算/变慢)。
    if provider_for_model(model) == "xiaomi":
        eb = kwargs.get("extra_body") or {}
        eb["thinking"] = {"type": "disabled"}
        kwargs["extra_body"] = eb

    t0 = time.perf_counter()
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as exc:  # noqa: BLE001
        # 该模型不支持 response_format → 去掉它重试一次(降级回 JSON-in-text)。
        if "response_format" in kwargs and "response_format" in str(exc).lower():
            kwargs.pop("response_format", None)
            resp = client.chat.completions.create(**kwargs)
        else:
            raise
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
        raw_args = first.function.arguments or "{}"
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            # Some models emit slightly-malformed tool-arg JSON (trailing commas,
            # unescaped quotes, truncation). Try to repair before giving up.
            try:
                from json_repair import repair_json
                repaired = json.loads(repair_json(raw_args))
                args = repaired if isinstance(repaired, dict) else {"_raw": raw_args}
            except Exception:
                args = {"_raw": raw_args}
        tool_use = {"name": first.function.name, "input": args}

    # Empty-output guard: reasoning models occasionally spend the whole token
    # budget on hidden reasoning and emit no content (and no tool call). That's
    # a transient failure — raise so the @retry wrapper re-runs the call. Only
    # treat as empty when there's genuinely nothing (no text AND no tool use).
    if not (text or "").strip() and tool_use is None:
        raise RuntimeError(
            f"empty LLM response (agent={agent}, model={model}, "
            f"finish={getattr(resp.choices[0], 'finish_reason', '?') if resp.choices else '?'}) — retrying"
        )

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


def call(*, agent: str, model: str, system, messages, tools=None, tool_choice=None,
         max_tokens: int = 4096, temperature: float = 0.7, top_p: float | None = None,
         response_format=None, extra_log=None) -> LLMResponse:
    """修复 E6:跨 provider 降级 wrapper(默认关闭)。
    - 未配 ``fallback_model``:直接透传 _call_impl,行为与历史完全一致(except 直接 re-raise)。
    - 配了 ``fallback_model``(应属另一 provider):主模型经重试仍失败后,降级到备用模型再试一次,
      避免单 provider 限流/宕机时整链失败或 ~14 分钟死等(配合 _adaptive_stop 限流快速短路)。"""
    kw = dict(agent=agent, model=model, system=system, messages=messages, tools=tools,
              tool_choice=tool_choice, max_tokens=max_tokens, temperature=temperature,
              top_p=top_p, response_format=response_format, extra_log=extra_log)
    try:
        return _call_impl(**kw)
    except Exception as primary_exc:
        fb = ""
        try:
            fb = get_fallback_model()
        except Exception:
            fb = ""
        if not fb or fb == model:
            raise
        import logging
        logging.getLogger(__name__).warning(
            "LLM 主模型 %s 失败,降级到 fallback_model=%s(agent=%s):%s", model, fb, agent, primary_exc)
        kw["model"] = fb
        return _call_impl(**kw)


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

    model, temperature, max_tokens, top_p = apply_overrides(
        agent, model=model, temperature=temperature, max_tokens=max_tokens, top_p=top_p,
    )
    client = get_client(model)
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
