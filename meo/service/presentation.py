from __future__ import annotations

from uuid import uuid4


_ALLOWED_KINDS = {"info", "status", "metric", "file", "system"}
_LIMITS = {
    "title": 120,
    "subtitle": 180,
    "value": 120,
    "detail": 1200,
}


def _bounded_text(card: dict, field: str) -> str:
    value = card.get(field, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"presentation card {field} must be a string")
    value = value.strip()
    if len(value) > _LIMITS[field]:
        raise ValueError(f"presentation card {field} is too long")
    return value


def normalize_presentation_card(event: dict) -> dict:
    """Normalize a backend card event into a bounded frontend-safe payload.

    Backends may emit ``{"type": "presentation_card", "card": {...}}``.
    The service accepts only data fields rendered by a registered native card.
    Arbitrary QML, HTML, JavaScript, URLs, commands and action payloads are not
    part of this contract.
    """

    if not isinstance(event, dict) or event.get("type") != "presentation_card":
        raise ValueError("unsupported presentation event")
    card = event.get("card")
    if not isinstance(card, dict):
        raise ValueError("presentation card payload is required")

    kind = card.get("kind", "info")
    if not isinstance(kind, str) or kind not in _ALLOWED_KINDS:
        raise ValueError("unsupported presentation card kind")

    title = _bounded_text(card, "title")
    if not title:
        raise ValueError("presentation card title is required")

    card_id = card.get("card_id")
    if card_id is None:
        card_id = f"card:{uuid4()}"
    if not isinstance(card_id, str) or not card_id.strip() or len(card_id) > 160:
        raise ValueError("presentation card_id is invalid")

    return {
        "type": "presentation.card",
        "card": {
            "card_id": card_id.strip(),
            "kind": kind,
            "title": title,
            "subtitle": _bounded_text(card, "subtitle"),
            "value": _bounded_text(card, "value"),
            "detail": _bounded_text(card, "detail"),
        },
    }
