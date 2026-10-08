from __future__ import annotations

from dataclasses import dataclass
import json
import threading
from typing import Dict
from uuid import uuid4

from meo.service.backend_adapter import BackendCallbacks, ModelInfo, SkillInfo


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

    Conversation IDs are persisted as additive metadata on Newelle chat records
    created through this adapter. Existing arbitrary Newelle chats are not silently
    adopted because that would make ownership ambiguous.
    """

    def __init__(self, interface) -> None:
        self.interface = interface
        self._conversations: Dict[str, int] = {}
        self._hydrate_conversations()

    @property
    def controller(self):
        return self.interface.controller

    def _workspace_chats(self):
        getter = getattr(self.controller, "workspace_chats", None)
        if callable(getter):
            try:
                return getter()
            except Exception:
                return {}
        chats = getattr(self.controller, "chats", None)
        return chats if isinstance(chats, dict) else {}

    def _hydrate_conversations(self) -> None:
        for chat_id, record in self._workspace_chats().items():
            if not isinstance(record, dict):
                continue
            conversation_id = record.get("meo_conversation_id")
            if isinstance(conversation_id, str) and conversation_id.startswith("meo:"):
                self._conversations.setdefault(conversation_id, chat_id)

    def _remember_conversation(self, conversation_id: str, chat_id: int) -> None:
        self._conversations[conversation_id] = chat_id
        record = self._workspace_chats().get(chat_id)
        if isinstance(record, dict):
            record["meo_conversation_id"] = conversation_id
            save = getattr(self.controller, "save_chats", None)
            if callable(save):
                save()

    def list_conversations(self):
        self._hydrate_conversations()
        chats = self._workspace_chats()
        result = []
        for conversation_id, chat_id in sorted(self._conversations.items()):
            record = chats.get(chat_id, {}) if isinstance(chats, dict) else {}
            result.append(
                {
                    "id": conversation_id,
                    "legacy_chat_id": chat_id,
                    "title": str(record.get("name", "")) if isinstance(record, dict) else "",
                }
            )
        return result

    def create_conversation(self) -> str:
        conversation_id = f"meo:{uuid4()}"
        chat_id = self.interface.get_or_create_chat(conversation_id)
        self._remember_conversation(conversation_id, chat_id)
        return conversation_id

    def conversation_exists(self, conversation_id: str) -> bool:
        self._hydrate_conversations()
        chat_id = self._conversations.get(conversation_id)
        return chat_id is not None and chat_id in self._workspace_chats()

    def attach_existing_session(self, conversation_id: str) -> int:
        """Register a known compatibility session and persist its chat ownership."""
        if not isinstance(conversation_id, str) or not conversation_id.startswith("meo:"):
            raise ValueError("legacy compatibility session must use a meo: key")
        chat_id = self.interface.get_or_create_chat(conversation_id)
        self._remember_conversation(conversation_id, chat_id)
        return chat_id

    def send_message(self, conversation_id: str, text: str, callbacks: BackendCallbacks):
        if not self.conversation_exists(conversation_id):
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
        self.controller.stop_workspace_request(execution_handle.chat_id)

    def list_models(self):
        """Return structured provider/model data using Newelle's existing handlers."""
        from src.constants import AVAILABLE_LLMS

        result = []
        for provider_name, provider_info in AVAILABLE_LLMS.items():
            try:
                handler_class = provider_info["class"]
                handler = handler_class(self.controller.settings, self.controller.handlers.directory)
                models = list(handler.get_models_list()) if hasattr(handler, "get_models_list") else []
            except Exception:
                continue
            provider_label = str(provider_info.get("title", provider_name))
            for model in models:
                if not model:
                    continue
                raw_id = str(model[0])
                label = str(model[1] if len(model) > 1 else model[0])
                result.append(ModelInfo(f"{provider_name}:{raw_id}", label, provider_label))
        return result

    def set_model(self, conversation_id: str, model_id: str) -> None:
        """Compatibility model switch.

        Newelle's current provider/model selection is process/profile scoped, not
        conversation-local. The AgentService API keeps the conversation argument so
        the compatibility limitation is explicit and can later be removed.
        """
        from src.constants import AVAILABLE_LLMS

        if not self.conversation_exists(conversation_id):
            raise ValueError("unknown conversation_id")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("model_id is required")

        if ":" in model_id:
            provider_name, raw_model_id = model_id.split(":", 1)
        else:
            provider_name = self.controller.newelle_settings.language_model
            raw_model_id = model_id
        if provider_name not in AVAILABLE_LLMS:
            raise ValueError(f"unknown model provider: {provider_name}")
        if not raw_model_id:
            raise ValueError("model_id is required")

        settings = self.controller.settings
        settings.set_string("language-model", provider_name)
        llm_settings = json.loads(settings.get_string("llm-settings"))
        llm_settings.setdefault(provider_name, {})["model"] = raw_model_id
        settings.set_string("llm-settings", json.dumps(llm_settings))
        self.controller.update_settings()

    def list_skills(self):
        manager = getattr(self.controller, "skill_manager", None)
        if manager is None:
            return []
        return [
            SkillInfo(skill.name, skill.name, manager.is_skill_enabled(skill.name))
            for skill in sorted(manager.skills.values(), key=lambda item: item.name.casefold())
        ]

    def set_skill_enabled(self, skill_id: str, enabled: bool) -> None:
        manager = getattr(self.controller, "skill_manager", None)
        if manager is None or skill_id not in manager.skills:
            raise ValueError(f"unknown skill_id: {skill_id}")
        manager.set_skill_enabled(skill_id, bool(enabled))

    def list_mcp_servers(self):
        # Newelle's MCP catalog/runtime is still coupled to extension/integration
        # structures. Keep this empty rather than parsing presentation text or
        # claiming a stable schema before the owning manager is identified.
        return []
