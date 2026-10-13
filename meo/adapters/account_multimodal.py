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
