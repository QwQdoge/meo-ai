from __future__ import annotations

from typing import Any

from meo.adapters.legacy_controls import LegacyAiControls
from meo.adapters.legacy_memory import LegacyMemoryBridge
from meo.service.backend_adapter import BackendCallbacks
from meo.service.response_meta import configured_context_from_usage


class ControlledLegacyBackend:
    """Add Meo product surfaces without widening the inherited chat adapter.

    Unknown attributes deliberately delegate to the wrapped backend so current
    AgentBackendAdapter/resource/presentation behavior remains unchanged. The
    wrappers keep Newelle-specific settings and memory storage behind typed Meo
    contracts that can be replaced independently later.
    """

    def __init__(self, backend, controller) -> None:
        self._backend = backend
        self._controller = controller
        self._controls = LegacyAiControls(controller)
        self._memory = LegacyMemoryBridge(controller)

    def __getattr__(self, name: str):
        return getattr(self._backend, name)

    def _setting_int(self, key: str) -> int | None:
        settings = getattr(self._controller, "settings", None)
        getter = getattr(settings, "get_int", None)
        if not callable(getter):
            return None
        try:
            value = getter(key)
        except Exception:
            return None
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

    def _effective_control_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        try:
            controls = self._controls.list_controls()
        except Exception:
            return values
        for control in controls:
            control_id = getattr(control, "control_id", "")
            if isinstance(control_id, str) and control_id:
                values[control_id] = getattr(control, "value", None)
        return values

    def _enrich_response_event(self, event: dict) -> dict:
        if event.get("type") != "response_meta":
            return event
        enriched = dict(event)
        usage = enriched.get("usage")
        enriched["context"] = configured_context_from_usage(
            usage if isinstance(usage, dict) else {},
            configured_budget=self._setting_int("context-max"),
            reserved_output_tokens=self._setting_int("suggested-tokens"),
        )
        enriched["controls"] = self._effective_control_values()
        return enriched

    def _wrap_callbacks(self, callbacks: BackendCallbacks) -> BackendCallbacks:
        return BackendCallbacks(
            on_text_delta=callbacks.on_text_delta,
            on_tool_event=lambda event: callbacks.on_tool_event(self._enrich_response_event(event)),
            on_done=callbacks.on_done,
            on_error=callbacks.on_error,
        )

    def send_message(self, conversation_id: str, text: str, callbacks: BackendCallbacks):
        return self._backend.send_message(conversation_id, text, self._wrap_callbacks(callbacks))

    def send_message_with_resources(self, conversation_id: str, text: str, resources, callbacks: BackendCallbacks):
        method = getattr(self._backend, "send_message_with_resources", None)
        if not callable(method):
            raise ValueError("selected backend does not support resource inputs")
        return method(conversation_id, text, resources, self._wrap_callbacks(callbacks))

    def list_controls(self):
        return self._controls.list_controls()

    def set_control(self, control_id: str, value: Any):
        return self._controls.set_control(control_id, value)

    def memory_supported(self) -> bool:
        return self._memory.supported()

    def memory_enabled(self) -> bool:
        return self._memory.memory_enabled()

    def set_memory_enabled(self, enabled: bool) -> bool:
        return self._memory.set_memory_enabled(enabled)

    def list_memories(self, *, scope: str | None = None, query: str = ""):
        return self._memory.list_memories(scope=scope, query=query)

    def create_memory(self, text: str, *, pinned: bool = False):
        return self._memory.create_memory(text, pinned=pinned)

    def update_memory(self, memory_id: str, *, text: str | None = None, pinned: bool | None = None):
        return self._memory.update_memory(memory_id, text=text, pinned=pinned)

    def delete_memory(self, memory_id: str) -> None:
        self._memory.delete_memory(memory_id)
