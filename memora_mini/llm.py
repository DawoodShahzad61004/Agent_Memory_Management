"""Chat-completions client for the single local endpoint.

Deliberately thin. No `tools=`, no `functions=`, no `.bind_tools()`, no
structured-output helper — every one of those compiles to a tool schema, and
the server behind CUSTOM_API_BASE does not support tool-calling. Structured
output is requested as plain JSON in the prompt and repaired in json_fix.py.
"""
from __future__ import annotations

import logging
import time

from openai import OpenAI

from memora_mini.config import (
    LLM_API_KEY,
    LLM_BACKOFF_BASE_SECONDS,
    LLM_BASE_URL,
    LLM_MAX_ATTEMPTS,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        if not LLM_BASE_URL:
            raise RuntimeError("CUSTOM_API_BASE is not set in LangMem/.env")
        _client = OpenAI(
            base_url=LLM_BASE_URL, api_key=LLM_API_KEY or "not-needed", timeout=LLM_TIMEOUT_SECONDS
        )
    return _client


def chat(system: str, user: str, *, max_tokens: int | None = None, temperature: float | None = None) -> str:
    """One chat completion, retried with backoff. Returns raw text."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last_error: Exception | None = None
    for attempt in range(1, LLM_MAX_ATTEMPTS + 1):
        try:
            response = client().chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                temperature=LLM_TEMPERATURE if temperature is None else temperature,
                max_tokens=max_tokens or LLM_MAX_TOKENS,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001 - one endpoint, one failure mode
            last_error = exc
            logger.warning("llm attempt %d/%d failed: %s", attempt, LLM_MAX_ATTEMPTS, exc)
            if attempt < LLM_MAX_ATTEMPTS:
                time.sleep(LLM_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
    raise RuntimeError(f"LLM call failed after {LLM_MAX_ATTEMPTS} attempts: {last_error}")


def is_reachable(timeout: float = 5.0) -> bool:
    """Cheap startup probe so demo.py fails fast with a useful message.

    Uses its own short-timeout client — the request-path timeout is 120s and a
    dead endpoint should not make the probe hang for two minutes.
    """
    if not LLM_BASE_URL:
        return False
    try:
        OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY or "not-needed",
               timeout=timeout, max_retries=0).models.list()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM endpoint %s unreachable: %s", LLM_BASE_URL, exc)
        return False
