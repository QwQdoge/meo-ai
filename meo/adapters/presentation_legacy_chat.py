from __future__ import annotations

from meo.adapters.legacy_chat import LegacyChatInterfaceAdapter
from meo.adapters.presentation_tools import decode_presentation_display
from meo.service.backend_adapter import BackendCallbacks


class MeoLegacyChatInterfaceAdapter(LegacyChatInterfaceAdapter):
    """Compatibility chat adapter that promotes Meo presentation tool results.

    Keep execution, resource input, timing and response metadata ownership in the
    base compatibility adapter. This layer only translates the private
    presentation-tool encoding into a typed presentation event.
    """

    def send_message(self, conversation_id: str, text: str, callbacks: BackendCallbacks):
        def on_tool_event(event: dict) -> None:
            presentation = decode_presentation_display(
                str(event.get("tool_name") or ""), event.get("display_text")
            )
            callbacks.on_tool_event(presentation if presentation is not None else event)

        wrapped = BackendCallbacks(
            on_text_delta=callbacks.on_text_delta,
            on_tool_event=on_tool_event,
            on_done=callbacks.on_done,
            on_error=callbacks.on_error,
        )
        return super().send_message(conversation_id, text, wrapped)
