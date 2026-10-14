from __future__ import annotations

from typing import Any, Mapping
import json
import re


BLOCK_TYPES = {
    "text",
    "markdown",
    "code",
    "math",
    "image",
    "attachment",
    "citation",
    "source_group",
    "tool_activity",
    "confirmation",
    "presentation",
    "chart",
    "table",
    "artifact",
    "html",
    "plugin",
    "error",
}

_MAX_ID = 160
_MAX_LABEL = 512
_MAX_TEXT = 256 * 1024
_MAX_DETAIL = 64 * 1024
_MAX_LANGUAGE = 64
_MAX_MIME = 128
_MAX_URI = 4096
_MAX_JSON = 512 * 1024
_MAX_ITEMS = 512
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:@/+\-]+$")


class ContentBlockError(ValueError):
    pass


def _bounded_text(value: Any, *, field: str, limit: int, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ContentBlockError(f"{field} must be a string")
    if required and not value.strip():
        raise ContentBlockError(f"{field} is required")
    if len(value) > limit:
        raise ContentBlockError(f"{field} exceeds {limit} characters")
    return value


def _stable_id(value: Any, *, field: str = "block_id") -> str:
    text = _bounded_text(value, field=field, limit=_MAX_ID, required=True)
    if not _SAFE_ID.fullmatch(text):
        raise ContentBlockError(f"{field} contains unsupported characters")
    return text


def _safe_size(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentBlockError("size_bytes must be an integer or null")
    if value < 0:
        raise ContentBlockError("size_bytes must be non-negative")
    return value


def _safe_positive_int(value: Any, *, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContentBlockError(f"{field} must be a positive integer or null")
    return value


def _bounded_json(value: Any, *, field: str, limit: int = _MAX_JSON) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ContentBlockError(f"{field} must be JSON-compatible") from exc
    if len(encoded.encode("utf-8")) > limit:
        raise ContentBlockError(f"{field} exceeds {limit} bytes")
    return value


def _bounded_list(value: Any, *, field: str, limit: int = _MAX_ITEMS) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ContentBlockError(f"{field} must be an array")
    if len(value) > limit:
        raise ContentBlockError(f"{field} contains too many items")
    return value


def _base(block: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    block_type = block.get("type")
    if block_type not in BLOCK_TYPES:
        raise ContentBlockError("unsupported content block type")
    normalized: dict[str, Any] = {
        "block_id": _stable_id(block.get("block_id")),
        "type": block_type,
    }
    return block_type, normalized


def normalize_content_block(block: Mapping[str, Any]) -> dict[str, Any]:
    """Return the bounded frontend-safe representation of one conversation block.

    This is a presentation/data boundary, not an execution boundary. Block action
    IDs are display/interaction handles only; executable work still goes through
    typed tool/Router contracts and their existing confirmation policy.

    HTML is presentation content only. Frontends must render it in an isolated
    sandbox with no native bridge. ``sandbox=static`` is the safe default.
    """

    if not isinstance(block, Mapping):
        raise ContentBlockError("content block must be an object")
    block_type, result = _base(block)

    if block_type in {"text", "markdown"}:
        result["text"] = _bounded_text(
            block.get("text"), field="text", limit=_MAX_TEXT, required=True
        )

    elif block_type == "code":
        result["text"] = _bounded_text(
            block.get("text"), field="text", limit=_MAX_TEXT, required=True
        )
        result["language"] = _bounded_text(
            block.get("language"), field="language", limit=_MAX_LANGUAGE
        )
        result["filename"] = _bounded_text(
            block.get("filename"), field="filename", limit=_MAX_LABEL
        )

    elif block_type == "math":
        result["latex"] = _bounded_text(
            block.get("latex"), field="latex", limit=_MAX_TEXT, required=True
        )
        result["display"] = bool(block.get("display", False))

    elif block_type in {"image", "attachment", "artifact"}:
        result["resource_id"] = _stable_id(block.get("resource_id"), field="resource_id")
        result["name"] = _bounded_text(
            block.get("name"), field="name", limit=_MAX_LABEL, required=True
        )
        result["mime_type"] = _bounded_text(
            block.get("mime_type"), field="mime_type", limit=_MAX_MIME
        )
        result["size_bytes"] = _safe_size(block.get("size_bytes"))
        result["state"] = _bounded_text(block.get("state"), field="state", limit=64)
        if block_type == "image":
            result["alt"] = _bounded_text(block.get("alt"), field="alt", limit=_MAX_LABEL)
            result["width"] = _safe_positive_int(block.get("width"), field="width")
            result["height"] = _safe_positive_int(block.get("height"), field="height")

    elif block_type == "citation":
        result["label"] = _bounded_text(
            block.get("label"), field="label", limit=_MAX_LABEL, required=True
        )
        result["uri"] = _bounded_text(block.get("uri"), field="uri", limit=_MAX_URI)
        result["detail"] = _bounded_text(
            block.get("detail"), field="detail", limit=_MAX_DETAIL
        )

    elif block_type == "source_group":
        result["title"] = _bounded_text(block.get("title"), field="title", limit=_MAX_LABEL)
        sources = _bounded_list(block.get("sources"), field="sources", limit=64)
        result["sources"] = _bounded_json(sources, field="sources")

    elif block_type == "tool_activity":
        result["activity_id"] = _stable_id(block.get("activity_id"), field="activity_id")
        result["title"] = _bounded_text(
            block.get("title"), field="title", limit=_MAX_LABEL, required=True
        )
        state = _bounded_text(block.get("state"), field="state", limit=64, required=True)
        if state not in {
            "queued",
            "running",
            "awaiting_confirmation",
            "completed",
            "failed",
            "cancelled",
        }:
            raise ContentBlockError("unsupported tool activity state")
        result["state"] = state
        result["detail"] = _bounded_text(
            block.get("detail"), field="detail", limit=_MAX_DETAIL
        )
        result["source"] = _bounded_text(block.get("source"), field="source", limit=128)

    elif block_type == "confirmation":
        result["decision_id"] = _stable_id(block.get("decision_id"), field="decision_id")
        result["title"] = _bounded_text(
            block.get("title"), field="title", limit=_MAX_LABEL, required=True
        )
        result["detail"] = _bounded_text(
            block.get("detail"), field="detail", limit=_MAX_DETAIL
        )
        actions = _bounded_list(block.get("actions"), field="actions", limit=16)
        result["actions"] = _bounded_json(actions, field="actions", limit=64 * 1024)

    elif block_type == "presentation":
        result["presentation_id"] = _stable_id(
            block.get("presentation_id"), field="presentation_id"
        )
        result["kind"] = _bounded_text(
            block.get("kind"), field="kind", limit=64, required=True
        )
        result["title"] = _bounded_text(
            block.get("title"), field="title", limit=_MAX_LABEL, required=True
        )
        result["value"] = _bounded_text(block.get("value"), field="value", limit=_MAX_LABEL)
        result["detail"] = _bounded_text(
            block.get("detail"), field="detail", limit=_MAX_DETAIL
        )

    elif block_type == "chart":
        result["chart_id"] = _stable_id(block.get("chart_id"), field="chart_id")
        kind = _bounded_text(block.get("kind"), field="kind", limit=32, required=True)
        if kind not in {"bar", "line", "pie", "scatter", "area"}:
            raise ContentBlockError("unsupported chart kind")
        result["kind"] = kind
        result["title"] = _bounded_text(block.get("title"), field="title", limit=_MAX_LABEL)
        result["x_key"] = _bounded_text(
            block.get("x_key"), field="x_key", limit=128, required=True
        )
        result["series"] = _bounded_json(
            _bounded_list(block.get("series"), field="series", limit=32), field="series"
        )
        result["data"] = _bounded_json(
            _bounded_list(block.get("data"), field="data", limit=_MAX_ITEMS), field="data"
        )

    elif block_type == "table":
        result["table_id"] = _stable_id(block.get("table_id"), field="table_id")
        result["title"] = _bounded_text(block.get("title"), field="title", limit=_MAX_LABEL)
        result["columns"] = _bounded_json(
            _bounded_list(block.get("columns"), field="columns", limit=64), field="columns"
        )
        result["rows"] = _bounded_json(
            _bounded_list(block.get("rows"), field="rows", limit=_MAX_ITEMS), field="rows"
        )

    elif block_type == "html":
        result["artifact_id"] = _stable_id(block.get("artifact_id"), field="artifact_id")
        result["title"] = _bounded_text(block.get("title"), field="title", limit=_MAX_LABEL)
        result["html"] = _bounded_text(
            block.get("html"), field="html", limit=_MAX_TEXT, required=True
        )
        sandbox = _bounded_text(block.get("sandbox", "static"), field="sandbox", limit=32)
        if sandbox not in {"static", "scripts", "interactive"}:
            raise ContentBlockError("unsupported HTML sandbox mode")
        result["sandbox"] = sandbox

    elif block_type == "plugin":
        presentation = block.get("presentation")
        if not isinstance(presentation, Mapping):
            raise ContentBlockError("presentation must be an object")
        plugin_id = _stable_id(presentation.get("plugin_id"), field="plugin_id")
        plugin_name = _bounded_text(
            presentation.get("plugin_name"), field="plugin_name", limit=_MAX_LABEL, required=True
        )
        normalized_presentation = {
            "plugin_id": plugin_id,
            "plugin_name": plugin_name,
            "icon_uri": _bounded_text(
                presentation.get("icon_uri"), field="icon_uri", limit=_MAX_URI
            ),
            "title": _bounded_text(
                presentation.get("title"), field="title", limit=_MAX_LABEL
            ),
            "subtitle": _bounded_text(
                presentation.get("subtitle"), field="subtitle", limit=_MAX_LABEL
            ),
            "body": _bounded_json(presentation.get("body", {}), field="body"),
            "actions": _bounded_json(
                _bounded_list(presentation.get("actions"), field="actions", limit=32),
                field="actions",
                limit=128 * 1024,
            ),
        }
        result["presentation"] = normalized_presentation

    elif block_type == "error":
        result["title"] = _bounded_text(
            block.get("title"), field="title", limit=_MAX_LABEL, required=True
        )
        result["detail"] = _bounded_text(
            block.get("detail"), field="detail", limit=_MAX_DETAIL
        )
        result["recoverable"] = bool(block.get("recoverable", False))

    return result


def normalize_content_blocks(blocks: Any) -> list[dict[str, Any]]:
    if not isinstance(blocks, list):
        raise ContentBlockError("content blocks must be an array")
    if len(blocks) > 128:
        raise ContentBlockError("too many content blocks")
    return [normalize_content_block(block) for block in blocks]


def legacy_text_block(*, block_id: str, role: str, text: str) -> dict[str, Any]:
    """Compatibility projection for inherited plain-text history."""

    block_type = "markdown" if role == "assistant" else "text"
    return normalize_content_block({
        "block_id": block_id,
        "type": block_type,
        "text": text,
    })
