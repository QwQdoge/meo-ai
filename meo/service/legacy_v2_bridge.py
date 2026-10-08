from __future__ import annotations

from typing import Dict, Tuple

from .request_state import RequestLifecycle, RequestState
from .tool_decision import ToolDecisionRegistry


class LegacyV2ToolBridge:
    """Translate Newelle v2 tool_interaction events into AgentService semantics.

    This module intentionally does not perform HTTP calls. It only normalizes the
    inherited event and maps a service-issued decision back to the legacy option
    index expected by the existing compatibility transport.
    """

    def __init__(self, decisions: ToolDecisionRegistry | None = None) -> None:
        self.decisions = decisions or ToolDecisionRegistry()
        self._legacy_indices: Dict[str, Tuple[int, ...]] = {}

    def publish(self, request: RequestLifecycle, event: dict) -> dict:
        if event.get("type") != "tool_interaction":
            raise ValueError("unsupported legacy tool event")
        if request.state is RequestState.RUNNING_MODEL:
            request.transition(RequestState.AWAITING_TOOL)
        if request.state is not RequestState.AWAITING_TOOL:
            raise ValueError("request is not ready for a tool decision")

        raw_options = event.get("options")
        if not isinstance(raw_options, list) or not raw_options:
            raise ValueError("legacy tool event has no options")

        titles = []
        legacy_indices = []
        normalized_options = []
        for position, raw in enumerate(raw_options):
            if not isinstance(raw, dict):
                raise ValueError("legacy tool option must be an object")
            title = raw.get("title")
            legacy_index = raw.get("index")
            if not isinstance(title, str) or not title.strip():
                raise ValueError("legacy tool option requires a title")
            if not isinstance(legacy_index, int) or isinstance(legacy_index, bool):
                raise ValueError("legacy tool option requires an integer index")
            titles.append(title)
            legacy_indices.append(legacy_index)
            normalized_options.append({"index": position, "title": title})

        decision = self.decisions.issue(request, titles)
        self._legacy_indices[decision.decision_id] = tuple(legacy_indices)
        return {
            "type": "tool.requested",
            "request_id": request.request_id,
            "decision_id": decision.decision_id,
            "tool_name": str(event.get("tool_name") or ""),
            "options": normalized_options,
            "compatibility": {
                "source": "newelle-v2",
                "interaction_id": event.get("interaction_id"),
            },
        }

    def resolve(self, request: RequestLifecycle, decision_id: str, option_index: int) -> int:
        indices = self._legacy_indices.get(decision_id)
        if indices is None:
            raise ValueError("unknown or expired compatibility decision")
        self.decisions.resolve(request, decision_id, option_index)
        try:
            legacy_index = indices[option_index]
        except IndexError as exc:
            raise ValueError("tool option index out of range") from exc
        self._legacy_indices.pop(decision_id, None)
        return legacy_index

    def cancel(self, request: RequestLifecycle) -> None:
        self.decisions.invalidate_for_request(request.request_id)
        stale = [
            decision_id
            for decision_id, decision in self.decisions._decisions.items()
            if decision.request_id == request.request_id
        ]
        for decision_id in stale:
            self._legacy_indices.pop(decision_id, None)
