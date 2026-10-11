from __future__ import annotations

import threading
import time

from meo.adapters.legacy_chat import LegacyChatInterfaceAdapter, LegacyExecutionHandle
from meo.adapters.presentation_tools import decode_presentation_display
from meo.service.backend_adapter import BackendCallbacks
from meo.system.account_ai_interaction import (
    AccountAiConsentInteraction,
    bind_account_ai_consent_sink,
)


class MeoLegacyChatInterfaceAdapter(LegacyChatInterfaceAdapter):
    """Meo compatibility layer for presentation cards and Account AI consent.

    Newelle keeps ownership of conversation history, the agent loop, tools and
    persistence.  This adapter adds only Meo product events. Account-provider
    consent is mapped onto the same typed tool-interaction channel already used
    by AgentService so the native client has one decision protocol.
    """

    def _publish_event(self, callbacks: BackendCallbacks, event: dict) -> None:
        presentation = decode_presentation_display(
            str(event.get("tool_name") or ""), event.get("display_text")
        )
        callbacks.on_tool_event(presentation if presentation is not None else event)

    def send_message(self, conversation_id: str, text: str, callbacks: BackendCallbacks):
        if not self.conversation_exists(conversation_id):
            raise ValueError("unknown conversation_id")

        handle = LegacyExecutionHandle(
            conversation_id=conversation_id,
            chat_id=self._conversations[conversation_id],
        )
        handle.pending_account_interaction = None
        started_at = time.monotonic()
        first_token_at: list[float | None] = [None]
        tool_names: list[str] = []

        def on_text_delta(delta: str) -> None:
            if delta and first_token_at[0] is None:
                first_token_at[0] = time.monotonic()
            callbacks.on_text_delta(delta)

        def on_tool_event(event: dict) -> None:
            tool_name = event.get("tool_name")
            if isinstance(tool_name, str) and tool_name:
                tool_names.append(tool_name)
            if event.get("type") == "tool_interaction":
                interaction_id = event.get("interaction_id")
                if not isinstance(interaction_id, str) or not interaction_id:
                    callbacks.on_error("legacy tool interaction is missing interaction_id")
                    return
                handle.pending_interaction_id = interaction_id
            self._publish_event(callbacks, event)

        def on_account_consent(interaction: AccountAiConsentInteraction) -> None:
            existing = getattr(handle, "pending_account_interaction", None)
            if existing is not None:
                raise RuntimeError("another Meo Account AI consent is already pending")
            handle.pending_account_interaction = interaction
            tool_names.append("Meo Account AI")
            self._publish_event(callbacks, interaction.public_event())

        def run() -> None:
            try:
                with bind_account_ai_consent_sink(on_account_consent):
                    self.interface.process_message(
                        conversation_id,
                        text,
                        on_chunk=on_text_delta,
                        on_tool_event=on_tool_event,
                    )
                callbacks.on_tool_event(self._response_meta_event(
                    handle.chat_id,
                    started_at=started_at,
                    first_token_at=first_token_at[0],
                    tool_names=tool_names,
                ))
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

    def choose_tool_option(self, execution_handle: LegacyExecutionHandle, legacy_option_index: int) -> None:
        interaction = getattr(execution_handle, "pending_account_interaction", None)
        if interaction is not None:
            if not interaction.resolve(legacy_option_index):
                raise ValueError("Meo Account AI consent is stale or already resolved")
            execution_handle.pending_account_interaction = None
            return
        super().choose_tool_option(execution_handle, legacy_option_index)

    def cancel(self, execution_handle: LegacyExecutionHandle) -> None:
        interaction = getattr(execution_handle, "pending_account_interaction", None)
        if interaction is not None:
            try:
                interaction.resolve(1)
            except Exception:
                pass
            execution_handle.pending_account_interaction = None
        super().cancel(execution_handle)
