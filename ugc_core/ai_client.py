"""LLM API client (OpenAI, Groq, or any OpenAI-compatible endpoint)."""

from __future__ import annotations

import json
import os
import re
import time
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


def normalize_api_key(key: str | None) -> str:
    """Strip whitespace, quotes, and newlines from pasted keys."""
    if not key:
        return ""
    k = key.strip().strip('"').strip("'").strip()
    # Sometimes secrets paste includes the variable name
    if "=" in k and k.upper().startswith("GROQ"):
        k = k.split("=", 1)[-1].strip().strip('"').strip("'")
    return k


def validate_groq_key(key: str) -> str | None:
    """Return error message if key looks invalid, else None."""
    k = normalize_api_key(key)
    if not k:
        return "No Groq API key found. Add it in the sidebar or Streamlit Secrets."
    if k.startswith("sk-") and not k.startswith("gsk_"):
        return "This looks like an OpenAI key (sk-...). For Groq, use a key starting with gsk_ from console.groq.com."
    if not k.startswith("gsk_"):
        return "Groq API keys start with gsk_. Create one at https://console.groq.com/keys"
    if len(k) < 20:
        return "API key seems too short. Copy the full key from Groq console."
    return None


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
        key = normalize_api_key(api_key or os.environ.get("GROQ_API_KEY", ""))
        return AIConfig(
            provider="groq",
            api_key=key,
            model=model or os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant"),
            base_url=base_url or "https://api.groq.com/openai/v1",
        ) if key else None

    if provider == "custom":
        key = (api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
        url = base_url or os.environ.get("OPENAI_BASE_URL", "").strip() or None
        mdl = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        return AIConfig(provider="custom", api_key=key, model=mdl, base_url=url) if key else None

    # default: openai
    key = normalize_api_key(api_key or os.environ.get("OPENAI_API_KEY", ""))
    if key:
        return AIConfig(
            provider="openai",
            api_key=key,
            model=model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            base_url=base_url,
        )

    # auto-fallback: groq if only groq key set
    groq = normalize_api_key(os.environ.get("GROQ_API_KEY", ""))
    if groq:
        return AIConfig(
            provider="groq",
            api_key=groq,
            model=model or os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant"),
            base_url="https://api.groq.com/openai/v1",
        )
    return None


def _retry_wait_seconds(error_message: str) -> float:
    m = re.search(r"try again in ([\d.]+)s", error_message, re.I)
    if m:
        return float(m.group(1)) + 1.5
    return 12.0


def chat_json(
    config: AIConfig,
    *,
    system: str,
    user: str,
    temperature: float = 0.5,
    max_retries: int = 5,
) -> dict[str, Any]:
    from openai import OpenAI

    kwargs: dict[str, Any] = {"api_key": config.api_key}
    if config.base_url:
        kwargs["base_url"] = config.base_url

    client = OpenAI(**kwargs)
    last_error: Exception | None = None

    for attempt in range(max_retries):
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
            raw = response.choices[0].message.content or "{}"
            try:
                return json.loads(raw)
            except json.JSONDecodeError as e:
                raise AIClientError(f"Invalid JSON from model: {e}") from e
        except Exception as e:
            last_error = e
            err_text = str(e)
            is_rate_limit = "429" in err_text or "rate_limit" in err_text.lower()
            if is_rate_limit and attempt < max_retries - 1:
                time.sleep(_retry_wait_seconds(err_text))
                continue
            break

    raise AIClientError(f"{config.provider} API error: {last_error}") from last_error
