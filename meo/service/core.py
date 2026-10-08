from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .legacy_v2_bridge import LegacyV2ToolBridge
from .request_registry import RequestRegistry
from .request_state import RequestLifecycle, RequestState


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    conversation_id: str


class AgentServiceCore:
    """Transport-independent Phase B request orchestration.

    The real Newelle-derived backend is deliberately outside this class. HTTP,
    D-Bus, QML and legacy controller code should translate to these operations
    instead of owning request/decision state themselves.
    """

    def __init__(self) -> None:
        self.requests = RequestRegistry()
        self.tool_bridge = LegacyV2ToolBridge()
        self._contexts: Dict[str, RequestContext] = {}

    def start_request(self, conversation_id: str) -> RequestContext:
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ValueError("conversation_id is required")
        request = self.requests.create()
        request.transition(RequestState.RUNNING_MODEL)
        context = RequestContext(request.request_id, conversation_id)
        self._contexts[request.request_id] = context
        return context

    def get_request(self, request_id: str) -> RequestLifecycle:
        return self.requests.get(request_id)

    def get_context(self, request_id: str) -> RequestContext:
        self.requests.get(request_id)
        try:
            return self._contexts[request_id]
        except KeyError as exc:
            raise ValueError("request has no context") from exc

    def publish_legacy_tool_request(self, request_id: str, event: dict) -> dict:
        request = self.requests.get(request_id)
        normalized = self.tool_bridge.publish(request, event)
        normalized["conversation_id"] = self.get_context(request_id).conversation_id
        return normalized

    def choose_tool_option(self, request_id: str, decision_id: str, option_index: int) -> int:
        request = self.requests.get(request_id)
        legacy_index = self.tool_bridge.resolve(request, decision_id, option_index)
        request.transition(RequestState.RUNNING_TOOL)
        return legacy_index

    def tool_completed(self, request_id: str) -> None:
        request = self.requests.get(request_id)
        if request.state is not RequestState.RUNNING_TOOL:
            raise ValueError("tool completion received while no tool is running")
        request.transition(RequestState.RUNNING_MODEL)

    def mark_external_effect_committed(self, request_id: str) -> None:
        self.requests.get(request_id).mark_external_effect_committed()

    def complete_request(self, request_id: str) -> None:
        request = self.requests.get(request_id)
        request.transition(RequestState.COMPLETED)

    def fail_request(self, request_id: str, error: str) -> None:
        self.requests.get(request_id).fail(error)

    def cancel_request(self, request_id: str) -> bool:
        request = self.requests.get(request_id)
        if request.terminal:
            return False
        request.request_cancel()
        self.tool_bridge.cancel(request)
        return True

    def acknowledge_cancelled(self, request_id: str) -> str:
        request = self.requests.get(request_id)
        request.mark_cancelled()
        return request.cancellation_summary()
