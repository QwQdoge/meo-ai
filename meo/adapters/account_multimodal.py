from __future__ import annotations

import json
import re
from typing import Mapping, Sequence


_IMAGE_BLOCK = re.compile(
    r"```image[^\S\r\n]*\r?\n(?P<source>data:image/[^\r\n]+)\r?\n```",
    re.IGNORECASE,
)
_ANY_IMAGE_BLOCK = re.compile(
    r"```image[^\S\r\n]*\r?\n.*?\r?\n```",
    re.IGNORECASE | re.DOTALL,
)
_MAX_INPUT_IMAGES = 8
_MAX_HISTORY_ITEMS = 48
_MAX_USER_PAYLOAD_CHARS = 40000
_MAX_CURRENT_PROMPT_CHARS = 32000


def account_model_supports_vision(
    connections: Sequence[Mapping[str, object]],
    raw_model_id: str,
) -> bool:
    """Return Account's explicit image-input capability for one exact model.

    `raw_model_id` is the Newelle model key exposed by the Account handler:
    `<connection-id>:<provider-model-id>`. Legacy connection records without an
    explicit `visionModels` list intentionally fail closed. Model names are
    never guessed from provider naming conventions.
    """

    if not isinstance(raw_model_id, str) or ":" not in raw_model_id:
        return False
    connection_id, model_id = raw_model_id.split(":", 1)
    connection_id = connection_id.strip()
    model_id = model_id.strip()
    if not connection_id or not model_id:
        return False

    for connection in connections:
        if not isinstance(connection, Mapping):
            continue
        if str(connection.get("id") or "").strip() != connection_id:
            continue
        configured = connection.get("visionModels")
        if not isinstance(configured, Sequence) or isinstance(configured, (str, bytes, bytearray)):
            return False
        return any(isinstance(value, str) and value == model_id for value in configured)
    return False


def strip_image_blocks(value: str) -> str:
    """Replace fenced image payloads with a bounded text marker.

    Historical image bytes must never be replayed into every later provider
    request. The current turn's image sources are extracted separately.
    """

    return _ANY_IMAGE_BLOCK.sub("[Image attachment]", value)


def context_payload(
    prompt: str,
    history: Sequence[Mapping[str, object]],
) -> tuple[str, tuple[str, ...]]:
    """Build the Account AI text context and current-turn image inputs.

    This helper is deliberately dependency-free so AgentService protocol tests
    do not import Newelle's optional desktop/image dependencies.
    """

    images = tuple(match.group("source").strip() for match in _IMAGE_BLOCK.finditer(prompt))
    if len(images) > _MAX_INPUT_IMAGES:
        raise ValueError(f"At most {_MAX_INPUT_IMAGES} images can be sent to Account AI")

    records: list[dict[str, str]] = []
    for item in history[-_MAX_HISTORY_ITEMS:]:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("User") or "").strip()
        message = item.get("Message")
        if not role or not isinstance(message, str) or not message:
            continue
        records.append({"role": role[:64], "content": strip_image_blocks(message)})

    clean_prompt = strip_image_blocks(prompt)
    payload: dict[str, object] = {
        "conversation_history": records,
        "current_user_prompt": clean_prompt,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) <= _MAX_USER_PAYLOAD_CHARS:
        return encoded, images

    # Preserve the current request and newest context. Remove oldest turns until
    # the broker's hard text limit is met; never silently truncate the current
    # user request itself.
    if len(clean_prompt) > _MAX_CURRENT_PROMPT_CHARS:
        raise ValueError("Current prompt is too large for the Account AI broker")
    while records:
        records.pop(0)
        payload["conversation_history"] = records
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) <= _MAX_USER_PAYLOAD_CHARS:
            return encoded, images
    if len(encoded) > _MAX_USER_PAYLOAD_CHARS:
        raise ValueError("Current prompt is too large for the Account AI broker")
    return encoded, images
