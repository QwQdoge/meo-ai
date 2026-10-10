from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "reasoning_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
)
_SENSITIVE_FRAGMENTS = (
    "authorization",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "cookie",
    "set-cookie",
)
_MAX_DEPTH = 8
_MAX_ITEMS = 256
_MAX_STRING = 64 * 1024


def _sensitive_key(key: str) -> bool:
    lowered = key.casefold().replace("-", "_")
    return any(fragment.replace("-", "_") in lowered for fragment in _SENSITIVE_FRAGMENTS)


def json_safe(value: Any, *, depth: int = 0) -> Any:
    """Bound arbitrary provider metadata to a JSON-safe, secret-filtered value.

    Meo AI keeps provider-returned metadata instead of throwing it away, but the
    native client must not accidentally surface credentials if a provider SDK
    includes request headers or credential-bearing debug fields in its response.
    """

    if depth > _MAX_DEPTH:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > _MAX_STRING:
            return value[:_MAX_STRING] + "…"
        return value
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for index, (raw_key, raw_value) in enumerate(value.items()):
            if index >= _MAX_ITEMS:
                result["__truncated__"] = True
                break
            key = str(raw_key)
            if _sensitive_key(key):
                result[key] = "<redacted>"
            else:
                result[key] = json_safe(raw_value, depth=depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result = [json_safe(item, depth=depth + 1) for item in value[:_MAX_ITEMS]]
        if len(value) > _MAX_ITEMS:
            result.append("<truncated>")
        return result
    return str(value)


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0:
        return None
    return value


def normalize_usage(usage: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(usage, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in _USAGE_KEYS:
        number = _number(usage.get(key))
        if number is not None:
            result[key] = number

    if "total_tokens" not in result:
        input_tokens = result.get("input_tokens")
        output_tokens = result.get("output_tokens")
        if isinstance(input_tokens, (int, float)) and isinstance(output_tokens, (int, float)):
            result["total_tokens"] = input_tokens + output_tokens

    extras = {
        str(key): json_safe(value)
        for key, value in usage.items()
        if key not in _USAGE_KEYS
    }
    if extras:
        result["extra"] = extras
    return result


def _pick(mapping: Mapping[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = mapping
        found = True
        for part in path.split("."):
            if not isinstance(current, Mapping) or part not in current:
                found = False
                break
            current = current[part]
        if found and current not in (None, ""):
            return current
    return None


def _reasoning_from_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    # Only expose reasoning text that the provider actually returned. Do not
    # synthesize or infer hidden chain-of-thought from ordinary answer text.
    raw = _pick(
        metadata,
        "reasoning",
        "reasoning_content",
        "output.reasoning",
        "message.reasoning",
        "choices.0.message.reasoning_content",
    )
    if isinstance(raw, str) and raw.strip():
        return {"available": True, "text": json_safe(raw)}
    if isinstance(raw, Mapping):
        safe = json_safe(raw)
        text = _pick(raw, "text", "content", "summary")
        result = {"available": True, "raw": safe}
        if isinstance(text, str) and text.strip():
            result["text"] = json_safe(text)
        return result
    return {"available": False}


def normalize_response_meta(event: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one backend response metadata event for UI/API consumers.

    Known fields get stable names while the complete JSON-safe provider payload
    remains under `provider_metadata`, so future APIs can add fields without a
    Meo AI release throwing them away.
    """

    metadata_raw = event.get("provider_metadata")
    metadata = metadata_raw if isinstance(metadata_raw, Mapping) else {}
    usage_raw = event.get("usage")
    usage = normalize_usage(usage_raw if isinstance(usage_raw, Mapping) else None)

    result: dict[str, Any] = {
        "type": "response.meta",
        "schema_version": 1,
        "usage": usage,
        "timing": {},
        "context": {},
        "reasoning": _reasoning_from_metadata(metadata),
        "activity": {},
        "provider_metadata": json_safe(metadata),
    }

    for key in ("provider", "model", "finish_reason", "response_id", "service_tier"):
        value = event.get(key)
        if value not in (None, ""):
            result[key] = json_safe(value)

    timing = event.get("timing")
    if isinstance(timing, Mapping):
        for key in ("total_ms", "first_token_ms", "first_visible_token_ms"):
            number = _number(timing.get(key))
            if number is not None:
                result["timing"][key] = number

    context = event.get("context")
    if isinstance(context, Mapping):
        for key in (
            "window_tokens",
            "used_tokens",
            "remaining_tokens",
            "trimmed_messages",
            "trimmed_tokens",
        ):
            number = _number(context.get(key))
            if number is not None:
                result["context"][key] = number
        for key in ("strategy", "status"):
            value = context.get(key)
            if isinstance(value, str) and value:
                result["context"][key] = value

    activity = event.get("activity")
    if isinstance(activity, Mapping):
        for key in ("memory", "search", "tools", "mcp", "web", "retrieval"):
            value = activity.get(key)
            if isinstance(value, (bool, int, float, str, list, dict)):
                result["activity"][key] = json_safe(value)

    citations = event.get("citations")
    if isinstance(citations, list):
        result["citations"] = json_safe(citations)

    # Preserve other backend-level fields too, without duplicating the normalized
    # envelope or exposing secrets.
    known = {
        "type", "provider", "model", "finish_reason", "response_id", "service_tier",
        "usage", "timing", "context", "activity", "citations", "provider_metadata",
    }
    extras = {str(key): json_safe(value) for key, value in event.items() if key not in known}
    if extras:
        result["extra"] = extras
    return result
