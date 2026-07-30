"""Three-tier repair for structured LLM output: fence-strip -> json_repair -> Pydantic.

There is no tool-calling and no structured-output helper anywhere in this
package, so this module is the *only* thing standing between an 8B model's
prose habits and a validated Pydantic object.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from memora_mini.memory.schemas import SCHEMA_REGISTRY  # noqa: F401 - registry lives with schemas

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def strip_fences(text: str) -> str:
    """Tier 1 — pull the payload out of markdown fences and surrounding prose."""
    if not text:
        return ""
    match = _FENCE.search(text)
    if match:
        text = match.group(1)
    text = text.strip()
    # Trim leading commentary ("Here is the JSON: [...]") by seeking the first
    # bracket and the matching last one.
    starts = [i for i in (text.find("["), text.find("{")) if i != -1]
    if starts:
        start = min(starts)
        end = max(text.rfind("]"), text.rfind("}"))
        if end > start:
            text = text[start : end + 1]
    return text.strip()


def parse_json(text: str) -> Any:
    """Tiers 1-2 — strip fences, then json.loads, then json_repair."""
    candidate = strip_fences(text)
    if not candidate:
        raise ValueError("empty LLM output")
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    from json_repair import repair_json

    repaired = repair_json(candidate, return_objects=True)
    if repaired in ("", None, [], {}):
        raise ValueError(f"unrepairable JSON: {text[:200]!r}")
    return repaired


def parse_list(text: str, schema: type[T], *, limit: int | None = None) -> list[T]:
    """Tier 3 — validate a JSON array against `schema`, dropping bad elements.

    Partial success beats total failure here: one malformed candidate out of
    three should not throw away the other two.
    """
    try:
        data = parse_json(text)
    except ValueError as exc:
        logger.warning("json_fix: %s", exc)
        return []
    if isinstance(data, dict):
        # 8B models like to wrap arrays in {"memories": [...]}.
        for value in data.values():
            if isinstance(value, list):
                data = value
                break
        else:
            data = [data]
    if not isinstance(data, list):
        return []
    out: list[T] = []
    for element in data:
        if not isinstance(element, dict):
            continue
        try:
            out.append(schema.model_validate(element))
        except ValidationError as exc:
            logger.warning("json_fix: dropped candidate: %s", exc.errors()[:2])
    return out[:limit] if limit else out


def parse_enum(text: str, allowed: tuple[str, ...], default: str) -> str:
    """Single-enum-token responses. Anything unrecognised falls back to `default`.

    Fail-safe by construction: for classification the default is UNRELATED,
    which means 'insert as new' — never 'mutate an existing record'.
    """
    if not text:
        return default
    upper = text.upper()
    hits = [token for token in allowed if re.search(rf"\b{re.escape(token)}\b", upper)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        # Ambiguous — take the earliest mention, which is usually the verdict.
        return min(hits, key=upper.find)
    return default
