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
    """Temporary adapter for the inherited Newelle ChatInterface API."""

    def __init__(self, interface) -> None:
        self.interface = interface
        self._conversations: Dict[str, int] = {}
        self._ambiguous_conversations: set[str] = set()
        self._hydrate_conversations()

    @property
    def controller(self):
        return self.interface.controller

    def _workspace_chats(self) -> dict:
        chats = getattr(self.controller, "chats", None)
        return chats if isinstance(chats, dict) else {}

    def _hydrate_conversations(self) -> None:
        discovered: Dict[str, int] = {}
        ambiguous: set[str] = set()
        for chat_id, chat in self._workspace_chats().items():
            if not isinstance(chat, dict):
                continue
            conversation_id = chat.get("meo_conversation_id")
            if not isinstance(conversation_id, str) or not conversation_id.startswith("meo:"):
                continue
            previous = discovered.get(conversation_id)
            if previous is not None and previous != chat_id:
                ambiguous.add(conversation_id)
                discovered.pop(conversation_id, None)
                continue
            if conversation_id not in ambiguous:
                discovered[conversation_id] = chat_id
        self._conversations = discovered
        self._ambiguous_conversations = ambiguous

    def _remember_conversation(self, conversation_id: str, chat_id: int) -> None:
        if conversation_id in self._ambiguous_conversations:
            raise ValueError("ambiguous conversation ownership")
        self._conversations[conversation_id] = chat_id
        chats = self._workspace_chats()
        chat = chats.get(chat_id)
        if isinstance(chat, dict):
            chat["meo_conversation_id"] = conversation_id
            save = getattr(self.controller, "save_chat", None)
            if callable(save):
                try:
                    save(chat_id)
                except TypeError:
                    save()

    def list_conversations(self):
        self._hydrate_conversations()
        return [
            {"id": conversation_id, "legacy_chat_id": chat_id}
            for conversation_id, chat_id in sorted(self._conversations.items())
            if chat_id in self._workspace_chats()
        ]

    def create_conversation(self) -> str:
        conversation_id = f"meo:{uuid4()}"
        chat_id = self.interface.get_or_create_chat(conversation_id)
        self._remember_conversation(conversation_id, chat_id)
        return conversation_id

    def conversation_exists(self, conversation_id: str) -> bool:
        self._hydrate_conversations()
        if conversation_id in self._ambiguous_conversations:
            return False
        chat_id = self._conversations.get(conversation_id)
        return chat_id is not None and chat_id in self._workspace_chats()

    def attach_existing_session(self, conversation_id: str) -> int:
        if not isinstance(conversation_id, str) or not conversation_id.startswith("meo:"):
            raise ValueError("legacy compatibility session must use a meo: key")
        self._hydrate_conversations()
        if conversation_id in self._ambiguous_conversations:
            raise ValueError("ambiguous conversation ownership")
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
                result.append(
                    ModelInfo(
                        f"{provider_name}:{raw_id}",
                        label,
                        provider_label,
                        selection_scope="profile",
                    )
                )
        return result

    def set_model(self, conversation_id: str, model_id: str) -> None:
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

        result = []
        for skill in sorted(manager.skills.values(), key=lambda item: item.name.casefold()):
            effective_enabled = bool(manager.is_skill_enabled(skill.name))
            try:
                configured_enabled = bool(manager.is_skill_enabled(skill.name, apply_overrides=False))
            except TypeError:
                configured_enabled = effective_enabled

            override_source = ""
            overrides = getattr(manager, "mode_skill_overrides", None)
            if isinstance(overrides, dict) and overrides.get(skill.name) in {"enable", "remove"}:
                override_source = "mode"

            result.append(
                SkillInfo(
                    skill.name,
                    skill.name,
                    effective_enabled,
                    configured_enabled=configured_enabled,
                    selection_scope="profile",
                    override_source=override_source,
                )
            )
        return result

    def set_skill_enabled(self, skill_id: str, enabled: bool) -> None:
        manager = getattr(self.controller, "skill_manager", None)
        if manager is None or skill_id not in manager.skills:
            raise ValueError(f"unknown skill_id: {skill_id}")
        manager.set_skill_enabled(skill_id, bool(enabled))

    def list_mcp_servers(self):
        return []
