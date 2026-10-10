from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


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


_USAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "input_tokens": ("input_tokens", "prompt_tokens"),
    "output_tokens": ("output_tokens", "completion_tokens"),
    "total_tokens": ("total_tokens",),
    "reasoning_tokens": (
        "reasoning_tokens",
        "output_tokens_details.reasoning_tokens",
        "completion_tokens_details.reasoning_tokens",
    ),
    "cache_read_tokens": (
        "cache_read_tokens",
        "cache_read_input_tokens",
        "input_tokens_details.cached_tokens",
        "prompt_tokens_details.cached_tokens",
    ),
    "cache_write_tokens": (
        "cache_write_tokens",
        "cache_creation_input_tokens",
    ),
    "audio_input_tokens": (
        "audio_input_tokens",
        "input_tokens_details.audio_tokens",
        "prompt_tokens_details.audio_tokens",
    ),
    "audio_output_tokens": (
        "audio_output_tokens",
        "output_tokens_details.audio_tokens",
        "completion_tokens_details.audio_tokens",
    ),
}

_PROVIDER_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "finish_reason": (
        "finish_reason",
        "choices.0.finish_reason",
        "output.finish_reason",
    ),
    "response_id": (
        "id",
        "response_id",
        "response.id",
    ),
    "request_id_provider": (
        "request_id",
        "request-id",
        "headers.x-request-id",
        "headers.request-id",
    ),
    "service_tier": (
        "service_tier",
        "serviceTier",
    ),
    "system_fingerprint": (
        "system_fingerprint",
        "systemFingerprint",
    ),
}


def _sensitive_key(key: str) -> bool:
    lowered = key.casefold().replace("-", "_")
    return any(fragment.replace("-", "_") in lowered for fragment in _SENSITIVE_FRAGMENTS)


def json_safe(value: Any, *, depth: int = 0) -> Any:
    """Bound arbitrary provider metadata to a JSON-safe, secret-filtered value.

    Meo AI intentionally keeps provider-returned metadata instead of throwing it
    away, but native clients must never accidentally surface credentials if an
    SDK includes request headers, cookies or credential-bearing debug fields.
    """

    if depth > _MAX_DEPTH:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= _MAX_STRING else value[:_MAX_STRING] + "…"
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for index, (raw_key, raw_value) in enumerate(value.items()):
            if index >= _MAX_ITEMS:
                result["__truncated__"] = True
                break
            key = str(raw_key)
            result[key] = "<redacted>" if _sensitive_key(key) else json_safe(raw_value, depth=depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result = [json_safe(item, depth=depth + 1) for item in value[:_MAX_ITEMS]]
        if len(value) > _MAX_ITEMS:
            result.append("<truncated>")
        return result
    return str(value)


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return value


def _pick(mapping: Mapping[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = mapping
        found = True
        for part in path.split("."):
            if isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    found = False
                    break
            elif isinstance(current, Mapping) and part in current:
                current = current[part]
            else:
                found = False
                break
        if found and current not in (None, ""):
            return current
    return None


def normalize_usage(usage: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(usage, Mapping):
        return {}

    result: dict[str, Any] = {}
    for canonical, aliases in _USAGE_ALIASES.items():
        number = _number(_pick(usage, *aliases))
        if number is not None:
            result[canonical] = number

    if "total_tokens" not in result:
        input_tokens = result.get("input_tokens")
        output_tokens = result.get("output_tokens")
        if isinstance(input_tokens, (int, float)) and isinstance(output_tokens, (int, float)):
            result["total_tokens"] = input_tokens + output_tokens

    safe_raw = json_safe(usage)
    if safe_raw:
        result["raw"] = safe_raw
    return result


def configured_context_from_usage(
    usage: Mapping[str, Any] | None,
    *,
    configured_budget: int | None,
    suggested_target: int | None = None,
) -> dict[str, Any]:
    """Describe the runtime's configured context budget without overstating it.

    ``context-max`` is an application budget, not a provider-certified model
    context-window size. ``context-suggested`` is a preferred working target,
    not an output-token limit. Prompt/input tokens are included only when the
    provider/runtime reported them for the actual request.
    """

    result: dict[str, Any] = {}
    if isinstance(configured_budget, int) and not isinstance(configured_budget, bool) and configured_budget > 0:
        result["window_tokens"] = configured_budget
        result["strategy"] = "configured_context_budget"
        result["status"] = "runtime_budget"
    if isinstance(suggested_target, int) and not isinstance(suggested_target, bool) and suggested_target > 0:
        result["target_tokens"] = suggested_target

    normalized = normalize_usage(usage)
    input_tokens = normalized.get("input_tokens")
    if isinstance(input_tokens, (int, float)):
        result["used_tokens"] = input_tokens
        if "window_tokens" in result:
            result["remaining_tokens"] = max(result["window_tokens"] - input_tokens, 0)
    return result


def _reasoning_from_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    raw = _pick(
        metadata,
        "reasoning",
        "reasoning_content",
        "reasoning_summary",
        "output.reasoning",
        "message.reasoning",
        "message.reasoning_content",
    )
    if isinstance(raw, str) and raw.strip():
        return {"available": True, "text": json_safe(raw), "provider_returned": True}
    if isinstance(raw, Mapping):
        safe = json_safe(raw)
        text = _pick(raw, "text", "content", "summary")
        result: dict[str, Any] = {
            "available": True,
            "provider_returned": True,
            "raw": safe,
        }
        if isinstance(text, str) and text.strip():
            result["text"] = json_safe(text)
        return result
    return {"available": False, "provider_returned": False}


def _safe_mapping(value: Any) -> dict[str, Any]:
    safe = json_safe(value) if isinstance(value, Mapping) else {}
    return safe if isinstance(safe, dict) else {}


def normalize_response_meta(event: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize provider/runtime metadata while retaining future API fields."""

    metadata_raw = event.get("provider_metadata")
    metadata = metadata_raw if isinstance(metadata_raw, Mapping) else {}
    usage_raw = event.get("usage")
    usage = normalize_usage(usage_raw if isinstance(usage_raw, Mapping) else None)

    result: dict[str, Any] = {
        "type": "response.meta",
        "schema_version": 2,
        "usage": usage,
        "timing": {},
        "context": {},
        "reasoning": _reasoning_from_metadata(metadata),
        "activity": {},
        "controls": _safe_mapping(event.get("controls")),
        "cost": _safe_mapping(event.get("cost")),
        "rate_limits": _safe_mapping(event.get("rate_limits")),
        "provider_metadata": json_safe(metadata),
    }

    for key in ("provider", "model"):
        value = event.get(key)
        if value not in (None, ""):
            result[key] = json_safe(value)

    for key, aliases in _PROVIDER_FIELD_ALIASES.items():
        value = event.get(key)
        if value in (None, ""):
            value = _pick(metadata, *aliases)
        if value not in (None, ""):
            result[key] = json_safe(value)

    timing = event.get("timing")
    if isinstance(timing, Mapping):
        for key in (
            "total_ms",
            "first_token_ms",
            "first_visible_token_ms",
            "queue_ms",
            "network_ms",
            "tool_ms",
            "reasoning_ms",
        ):
            number = _number(timing.get(key))
            if number is not None:
                result["timing"][key] = number
        for key in ("started_at", "completed_at"):
            value = timing.get(key)
            if isinstance(value, str) and value:
                result["timing"][key] = value

    context = event.get("context")
    if isinstance(context, Mapping):
        for key in (
            "window_tokens",
            "target_tokens",
            "used_tokens",
            "remaining_tokens",
            "max_output_tokens",
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
        window_tokens = result["context"].get("window_tokens")
        used_tokens = result["context"].get("used_tokens")
        if isinstance(window_tokens, (int, float)) and window_tokens > 0 and isinstance(used_tokens, (int, float)):
            result["context"]["percent_used"] = round((used_tokens / window_tokens) * 100, 2)

    activity = event.get("activity")
    if isinstance(activity, Mapping):
        for key in (
            "memory",
            "search",
            "tools",
            "mcp",
            "web",
            "retrieval",
            "files",
            "vision",
            "code",
            "sync",
        ):
            value = activity.get(key)
            if isinstance(value, (bool, int, float, str, list, dict)):
                result["activity"][key] = json_safe(value)

    citations = event.get("citations")
    if isinstance(citations, list):
        result["citations"] = json_safe(citations)

    known = {
        "type",
        "provider",
        "model",
        "finish_reason",
        "response_id",
        "request_id_provider",
        "service_tier",
        "system_fingerprint",
        "usage",
        "timing",
        "context",
        "activity",
        "controls",
        "cost",
        "rate_limits",
        "citations",
        "provider_metadata",
    }
    extras = {str(key): json_safe(value) for key, value in event.items() if key not in known}
    if extras:
        result["extra"] = extras
    return result
