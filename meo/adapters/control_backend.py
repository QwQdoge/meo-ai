from __future__ import annotations

from typing import Any

from meo.adapters.legacy_controls import LegacyAiControls


class ControlledLegacyBackend:
    """Add Meo's typed control surface without widening the chat adapter.

    Unknown attributes deliberately delegate to the wrapped backend so current
    AgentBackendAdapter/resource/presentation behavior remains unchanged. This is
    a migration seam: when Newelle settings disappear, only this wrapper/control
    adapter needs replacement.
    """

    def __init__(self, backend, controller) -> None:
        self._backend = backend
        self._controls = LegacyAiControls(controller)

    def __getattr__(self, name: str):
        return getattr(self._backend, name)

    def list_controls(self):
        return self._controls.list_controls()

    def set_control(self, control_id: str, value: Any):
        return self._controls.set_control(control_id, value)
