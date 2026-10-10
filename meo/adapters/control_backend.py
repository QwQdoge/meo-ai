from __future__ import annotations

from typing import Any

from meo.adapters.legacy_controls import LegacyAiControls
from meo.adapters.legacy_memory import LegacyMemoryBridge


class ControlledLegacyBackend:
    """Add Meo product surfaces without widening the inherited chat adapter.

    Unknown attributes deliberately delegate to the wrapped backend so current
    AgentBackendAdapter/resource/presentation behavior remains unchanged. The
    wrappers keep Newelle-specific settings and memory storage behind typed Meo
    contracts that can be replaced independently later.
    """

    def __init__(self, backend, controller) -> None:
        self._backend = backend
        self._controls = LegacyAiControls(controller)
        self._memory = LegacyMemoryBridge(controller)

    def __getattr__(self, name: str):
        return getattr(self._backend, name)

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
