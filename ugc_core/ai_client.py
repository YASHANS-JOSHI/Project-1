"""LLM API client (OpenAI, Groq, or any OpenAI-compatible endpoint)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class AIConfig:
    provider: str  # openai | groq | custom
    api_key: str
    model: str
    base_url: str | None = None


class AIClientError(Exception):
    pass


def resolve_ai_config(
    *,
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> AIConfig | None:
    """Pick first available provider from args or environment."""
    provider = (provider or os.environ.get("AI_PROVIDER", "openai")).lower().strip()

    if provider == "groq":
        key = (api_key or os.environ.get("GROQ_API_KEY", "")).strip()
        return AIConfig(
            provider="groq",
            api_key=key,
            model=model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            base_url=base_url or "https://api.groq.com/openai/v1",
        ) if key else None

    if provider == "custom":
        key = (api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
        url = base_url or os.environ.get("OPENAI_BASE_URL", "").strip() or None
        mdl = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        return AIConfig(provider="custom", api_key=key, model=mdl, base_url=url) if key else None

    # default: openai
    key = (api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
    if key:
        return AIConfig(
            provider="openai",
            api_key=key,
            model=model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            base_url=base_url,
        )

    # auto-fallback: groq if only groq key set
    groq = os.environ.get("GROQ_API_KEY", "").strip()
    if groq:
        return AIConfig(
            provider="groq",
            api_key=groq,
            model=model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            base_url="https://api.groq.com/openai/v1",
        )
    return None


def chat_json(
    config: AIConfig,
    *,
    system: str,
    user: str,
    temperature: float = 0.5,
) -> dict[str, Any]:
    from openai import OpenAI

    kwargs: dict[str, Any] = {"api_key": config.api_key}
    if config.base_url:
        kwargs["base_url"] = config.base_url

    client = OpenAI(**kwargs)
    try:
        response = client.chat.completions.create(
            model=config.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        raise AIClientError(f"{config.provider} API error: {e}") from e

    raw = response.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise AIClientError(f"Invalid JSON from model: {e}") from e
