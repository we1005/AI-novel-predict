from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel

from ..config import DEFAULT_PROVIDER, OPENAI_BASE_URL, PROVIDERS
from . import store

router = APIRouter()


@router.get("")
def settings_get() -> dict[str, Any]:
    return store.get_settings()


class UpdatePayload(BaseModel):
    default_model_fast: str | None = None
    default_model_strong: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    providers: dict[str, dict[str, Any]] | None = None
    agents: dict[str, dict[str, Any]] | None = None


@router.put("")
def settings_put(body: UpdatePayload) -> dict[str, Any]:
    return store.update_settings(body.model_dump(exclude_none=True))


@router.post("/reset")
def settings_reset() -> dict[str, Any]:
    return store.reset_settings()


class TestKeyPayload(BaseModel):
    api_key: str | None = None       # if omitted → use currently saved key
    base_url: str | None = None
    model: str | None = None
    provider: str | None = None      # if given, test this provider's creds


# Per-provider sensible default model for the ping test.
_PROVIDER_PING_MODEL = {
    "dashscope": "qwen3.5-flash",
    "volc": "doubao-seed-2.0-lite",
}


@router.post("/test-key")
def settings_test_key(body: TestKeyPayload) -> dict[str, Any]:
    """Round-trip a tiny prompt to verify the key/base_url work.

    Resolution order for which provider to test:
      explicit ``provider`` → the provider implied by ``model`` → default.
    """
    model = (body.model or "").strip()
    pid = (body.provider or "").strip()
    if not pid:
        pid = store.provider_for_model(model) if model else DEFAULT_PROVIDER
    if pid not in PROVIDERS:
        pid = DEFAULT_PROVIDER

    saved_key, saved_url = store.resolve_provider_creds(pid)
    key = (body.api_key or "").strip() or saved_key
    url = (body.base_url or "").strip() or saved_url or OPENAI_BASE_URL
    model = model or _PROVIDER_PING_MODEL.get(pid, "qwen3.5-flash")
    if not key:
        raise HTTPException(400, f"no api key for provider '{pid}'")
    try:
        c = OpenAI(api_key=key, base_url=url)
        resp = c.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=4,
            temperature=0,
        )
        msg = resp.choices[0].message.content if resp.choices else ""
        return {"ok": True, "provider": pid, "model": model, "base_url": url,
                "sample": (msg or "")[:40]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "provider": pid, "error": str(e)[:240]}
