from __future__ import annotations

import json
from typing import Any

from meo.service.presentation import normalize_presentation_card


_PRESENTATION_PREFIX = "__MEO_PRESENTATION_CARD_V1__"
_TOOL_NAME = "meo_present_card"


def encode_presentation_display(card: dict[str, Any]) -> str:
    """Encode a card through the legacy ToolResult display_text seam.

    This value is consumed inside the Meo-owned compatibility adapter before it
    reaches AgentService/QML. It is not a public frontend protocol and carries
    no action or permission authority.
    """

    normalized = normalize_presentation_card({"type": "presentation_card", "card": card})
    return _PRESENTATION_PREFIX + json.dumps(
        normalized["card"], ensure_ascii=False, separators=(",", ":")
    )


def decode_presentation_display(tool_name: str, display_text: Any) -> dict | None:
    if tool_name != _TOOL_NAME or not isinstance(display_text, str):
        return None
    if not display_text.startswith(_PRESENTATION_PREFIX):
        return None
    try:
        card = json.loads(display_text[len(_PRESENTATION_PREFIX):])
    except json.JSONDecodeError as exc:
        raise ValueError("invalid Meo presentation card payload") from exc
    # Re-normalize at the adapter boundary; AgentService performs the same
    # validation again before publishing to a native client.
    normalized = normalize_presentation_card({"type": "presentation_card", "card": card})
    return {"type": "presentation_card", "card": normalized["card"]}


class NewellePresentationToolAdapter:
    """Expose a data-only native presentation tool to the compatibility model."""

    tool_name = _TOOL_NAME

    def __init__(self, *, _tool_types: tuple[type, type] | None = None) -> None:
        self._tool_types_override = _tool_types
        self._installed_controller = None
        self._original_require_tool_update = None

    def _tool_types(self):
        if self._tool_types_override is not None:
            return self._tool_types_override
        # Compatibility-only dependency: src.tools imports GLib. Keep that import
        # outside stable service/presentation contracts.
        from src.tools import Tool, ToolResult

        return Tool, ToolResult

    @staticmethod
    def _schema() -> dict:
        return {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["info", "status", "metric", "file", "system"],
                    "description": "Native card presentation kind.",
                },
                "title": {"type": "string", "maxLength": 120},
                "subtitle": {"type": "string", "maxLength": 180},
                "value": {"type": "string", "maxLength": 120},
                "detail": {"type": "string", "maxLength": 1200},
            },
            "required": ["kind", "title"],
            "additionalProperties": False,
        }

    def _execute(
        self,
        kind: str,
        title: str,
        subtitle: str = "",
        value: str = "",
        detail: str = "",
    ):
        _Tool, ToolResult = self._tool_types()
        card = {
            "kind": kind,
            "title": title,
            "subtitle": subtitle,
            "value": value,
            "detail": detail,
        }
        result = ToolResult(display_text=encode_presentation_display(card))
        result.set_output(
            json.dumps(
                {"presented": True, "kind": kind, "title": title},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return result

    def build_tool(self):
        Tool, _ToolResult = self._tool_types()
        return Tool(
            self.tool_name,
            (
                "Show one compact native Meo AI card next to the conversation. "
                "Use this only for presentation of useful structured results such as "
                "status, metrics, file summaries, or system state. The card is data-only, "
                "has no side effects, and never replaces a permission/confirmation tool. "
                "Call it multiple times when several small cards are genuinely useful."
            ),
            self._execute,
            schema=self._schema(),
            title="Present native card",
            prompt_editable=False,
            default_on=True,
            tools_group="Meo UI",
            default_lazy_load=False,
        )

    def register_into(self, registry) -> None:
        existing = getattr(registry, "get_tool", lambda _name: None)(self.tool_name)
        if existing is not None:
            return
        registry.register_tool(self.build_tool())

    def install(self, controller) -> None:
        if self._installed_controller is not None:
            if self._installed_controller is controller:
                return
            raise RuntimeError("Presentation tool adapter is already installed on another controller")

        original = controller.require_tool_update
        self._installed_controller = controller
        self._original_require_tool_update = original

        def require_tool_update():
            result = original()
            self.register_into(controller.tools)
            return result

        controller.require_tool_update = require_tool_update
        self.register_into(controller.tools)
