from __future__ import annotations

import threading

from meo.adapters.legacy_chat import LegacyChatInterfaceAdapter, LegacyExecutionHandle
from meo.adapters.presentation_tools import decode_presentation_display
from meo.service.backend_adapter import BackendCallbacks


class MeoLegacyChatInterfaceAdapter(LegacyChatInterfaceAdapter):
    """Compatibility chat adapter that promotes Meo presentation tool results.

    Upstream ChatInterface exposes only generic tool-result events. Keep the
    presentation encoding private to this Meo-owned seam and translate it back
    to a typed presentation event before AgentService sees it.
    """

    def send_message(self, conversation_id: str, text: str, callbacks: BackendCallbacks):
        if not self.conversation_exists(conversation_id):
            raise ValueError("unknown conversation_id")
        handle = LegacyExecutionHandle(
            conversation_id=conversation_id,
            chat_id=self._conversations[conversation_id],
        )

        def on_tool_event(event: dict) -> None:
            presentation = decode_presentation_display(
                str(event.get("tool_name") or ""), event.get("display_text")
            )
            if presentation is not None:
                callbacks.on_tool_event(presentation)
                return

            if event.get("type") == "tool_interaction":
                interaction_id = event.get("interaction_id")
                if not isinstance(interaction_id, str) or not interaction_id:
                    callbacks.on_error("legacy tool interaction is missing interaction_id")
                    return
                handle.pending_interaction_id = interaction_id
            callbacks.on_tool_event(event)

        def run() -> None:
            try:
                self.interface.process_message(
                    conversation_id,
                    text,
                    on_chunk=callbacks.on_text_delta,
                    on_tool_event=on_tool_event,
                )
            except Exception as exc:
                callbacks.on_error(str(exc))
                return
            callbacks.on_done()

        handle.thread = threading.Thread(
            target=run,
            name=f"meo-legacy-agent-{handle.chat_id}",
            daemon=True,
        )
        handle.thread.start()
        return handle
