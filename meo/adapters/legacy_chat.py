from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Dict
from uuid import uuid4

from meo.service.backend_adapter import BackendCallbacks


@dataclass
class LegacyExecutionHandle:
    conversation_id: str
    chat_id: int
    thread: threading.Thread | None = None
    pending_interaction_id: str | None = None


class LegacyChatInterfaceAdapter:
    """Temporary adapter for the inherited Newelle ChatInterface API.

    The caller injects an already-constructed ChatInterface-like object. This
    module does not import Newelle controller/UI modules itself, which keeps the
    AgentService boundary testable while GTK-era construction remains elsewhere.

    Conversation IDs in this adapter are compatibility session keys. Durable
    history discovery/resume across arbitrary existing Newelle chats is not yet
    implemented and must not be claimed by callers.
    """

    def __init__(self, interface) -> None:
        self.interface = interface
        self._conversations: Dict[str, int] = {}

    def list_conversations(self):
        return [
            {"id": conversation_id, "legacy_chat_id": chat_id}
            for conversation_id, chat_id in sorted(self._conversations.items())
        ]

    def create_conversation(self) -> str:
        conversation_id = f"meo:{uuid4()}"
        chat_id = self.interface.get_or_create_chat(conversation_id)
        self._conversations[conversation_id] = chat_id
        return conversation_id

    def conversation_exists(self, conversation_id: str) -> bool:
        return conversation_id in self._conversations

    def attach_existing_session(self, conversation_id: str) -> int:
        """Register a known compatibility session without inventing chat state."""
        if not isinstance(conversation_id, str) or not conversation_id.startswith("meo:"):
            raise ValueError("legacy compatibility session must use a meo: key")
        chat_id = self.interface.get_or_create_chat(conversation_id)
        self._conversations[conversation_id] = chat_id
        return chat_id

    def send_message(self, conversation_id: str, text: str, callbacks: BackendCallbacks):
        if conversation_id not in self._conversations:
            raise ValueError("unknown conversation_id")
        handle = LegacyExecutionHandle(
            conversation_id=conversation_id,
            chat_id=self._conversations[conversation_id],
        )

        def on_tool_event(event: dict) -> None:
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

    def choose_tool_option(self, execution_handle: LegacyExecutionHandle, legacy_option_index: int) -> None:
        interaction_id = execution_handle.pending_interaction_id
        if not interaction_id:
            raise ValueError("no pending legacy tool interaction")
        if not self.interface.resolve_pending_interaction(interaction_id, legacy_option_index):
            raise ValueError("legacy tool interaction is stale or invalid")
        execution_handle.pending_interaction_id = None

    def cancel(self, execution_handle: LegacyExecutionHandle) -> None:
        controller = self.interface.controller
        controller.stop_workspace_request(execution_handle.chat_id)

    def list_models(self):
        return []

    def set_model(self, conversation_id: str, model_id: str) -> None:
        raise NotImplementedError("model switching is not exposed by the legacy adapter yet")

    def list_skills(self):
        return []

    def set_skill_enabled(self, skill_id: str, enabled: bool) -> None:
        raise NotImplementedError("skill toggling is not exposed by the legacy adapter yet")

    def list_mcp_servers(self):
        return []
