from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import re


BLOCK_TYPES = {
    "text",
    "markdown",
    "code",
    "image",
    "attachment",
    "citation",
    "tool_activity",
    "confirmation",
    "presentation",
    "artifact",
    "error",
}

_MAX_ID = 160
_MAX_LABEL = 512
_MAX_TEXT = 256 * 1024
_MAX_DETAIL = 64 * 1024
_MAX_LANGUAGE = 64
_MAX_MIME = 128
_MAX_URI = 4096
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

    This is a presentation/data boundary, not an execution boundary. It intentionally
    rejects arbitrary action payloads, local paths, shell commands, QML, HTML and
    JavaScript. Executable actions continue through typed tool/Router contracts.
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

    elif block_type in {"image", "attachment", "artifact"}:
        result["resource_id"] = _stable_id(block.get("resource_id"), field="resource_id")
        result["name"] = _bounded_text(
            block.get("name"), field="name", limit=_MAX_LABEL, required=True
        )
        result["mime_type"] = _bounded_text(
            block.get("mime_type"), field="mime_type", limit=_MAX_MIME
        )
        result["size_bytes"] = _safe_size(block.get("size_bytes"))
        result["state"] = _bounded_text(
            block.get("state"), field="state", limit=64
        )
        if block_type == "image":
            width = block.get("width")
            height = block.get("height")
            for field, value in (("width", width), ("height", height)):
                if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value <= 0):
                    raise ContentBlockError(f"{field} must be a positive integer or null")
                result[field] = value

    elif block_type == "citation":
        result["label"] = _bounded_text(
            block.get("label"), field="label", limit=_MAX_LABEL, required=True
        )
        result["uri"] = _bounded_text(
            block.get("uri"), field="uri", limit=_MAX_URI
        )
        result["detail"] = _bounded_text(
            block.get("detail"), field="detail", limit=_MAX_DETAIL
        )

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
        result["source"] = _bounded_text(
            block.get("source"), field="source", limit=128
        )

    elif block_type == "confirmation":
        result["decision_id"] = _stable_id(block.get("decision_id"), field="decision_id")
        result["title"] = _bounded_text(
            block.get("title"), field="title", limit=_MAX_LABEL, required=True
        )
        result["detail"] = _bounded_text(
            block.get("detail"), field="detail", limit=_MAX_DETAIL
        )

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
        result["value"] = _bounded_text(
            block.get("value"), field="value", limit=_MAX_LABEL
        )
        result["detail"] = _bounded_text(
            block.get("detail"), field="detail", limit=_MAX_DETAIL
        )

    elif block_type == "error":
        result["title"] = _bounded_text(
            block.get("title"), field="title", limit=_MAX_LABEL, required=True
        )
        result["detail"] = _bounded_text(
            block.get("detail"), field="detail", limit=_MAX_DETAIL
        )
        result["recoverable"] = bool(block.get("recoverable", False))

    # Deliberately no generic payload/actions/path/command/html/qml/js fields.
    return result


def normalize_content_blocks(blocks: Any) -> list[dict[str, Any]]:
    if not isinstance(blocks, list):
        raise ContentBlockError("content blocks must be an array")
    if len(blocks) > 128:
        raise ContentBlockError("too many content blocks")
    return [normalize_content_block(block) for block in blocks]


def legacy_text_block(*, block_id: str, role: str, text: str) -> dict[str, Any]:
    """Compatibility projection for inherited plain-text history.

    Assistant text is treated as Markdown-capable presentation, while user text
    remains plain text so pasted markup is not reinterpreted as authored UI.
    """

    block_type = "markdown" if role == "assistant" else "text"
    return normalize_content_block({
        "block_id": block_id,
        "type": block_type,
        "text": text,
    })
