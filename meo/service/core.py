from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable, Dict

from .backend_adapter import AgentBackendAdapter, BackendCallbacks
from .legacy_v2_bridge import LegacyV2ToolBridge
from .request_registry import RequestRegistry
from .request_state import RequestLifecycle, RequestState


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    conversation_id: str


class AgentServiceCore:
    """Transport-independent Phase B request orchestration.

    A backend adapter may wrap the current Newelle-derived controller or a later
    extracted headless core. HTTP, D-Bus, QML and legacy controller code should
    translate to these operations instead of owning request/decision state.
    """

    def __init__(self, backend: AgentBackendAdapter | None = None) -> None:
        self.backend = backend
        self.requests = RequestRegistry()
        self.tool_bridge = LegacyV2ToolBridge()
        self._contexts: Dict[str, RequestContext] = {}
        self._execution_handles: Dict[str, object] = {}

    def _require_backend(self) -> AgentBackendAdapter:
        if self.backend is None:
            raise RuntimeError("AgentServiceCore has no backend adapter")
        return self.backend

    def list_conversations(self) -> list[dict]:
        return list(self._require_backend().list_conversations())

    def create_conversation(self) -> str:
        conversation_id = self._require_backend().create_conversation()
        if not isinstance(conversation_id, str) or not conversation_id:
            raise RuntimeError("backend returned an invalid conversation ID")
        return conversation_id

    def list_messages(self, conversation_id: str) -> list[dict]:
        backend = self._require_backend()
        if not backend.conversation_exists(conversation_id):
            raise ValueError("unknown conversation_id")
        messages = []
        for item in backend.list_messages(conversation_id):
            if item.role not in {"user", "assistant"}:
                raise RuntimeError("backend returned an invalid conversation role")
            if not isinstance(item.text, str):
                raise RuntimeError("backend returned invalid conversation text")
            messages.append({"role": item.role, "text": item.text})
        return messages

    def list_models(self) -> list[dict]:
        return [
            {
                "model_id": item.model_id,
                "label": item.label,
                "provider": item.provider,
                "selection_scope": item.selection_scope,
            }
            for item in self._require_backend().list_models()
        ]

    def set_model(self, conversation_id: str, model_id: str) -> None:
        backend = self._require_backend()
        if not backend.conversation_exists(conversation_id):
            raise ValueError("unknown conversation_id")
        backend.set_model(conversation_id, model_id)

    def list_skills(self) -> list[dict]:
        return [
            {
                "skill_id": item.skill_id,
                "label": item.label,
                "enabled": item.enabled,
                "configured_enabled": item.configured_enabled,
                "selection_scope": item.selection_scope,
                "override_source": item.override_source,
            }
            for item in self._require_backend().list_skills()
        ]

    def set_skill_enabled(self, skill_id: str, enabled: bool) -> None:
        if not isinstance(skill_id, str) or not skill_id:
            raise ValueError("skill_id is required")
        self._require_backend().set_skill_enabled(skill_id, bool(enabled))

    def list_mcp_servers(self) -> list[dict]:
        return [
            {"server_id": item.server_id, "label": item.label, "enabled": item.enabled}
            for item in self._require_backend().list_mcp_servers()
        ]

    def start_request(self, conversation_id: str) -> RequestContext:
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ValueError("conversation_id is required")
        request = self.requests.create()
        request.transition(RequestState.RUNNING_MODEL)
        context = RequestContext(request.request_id, conversation_id)
        self._contexts[request.request_id] = context
        return context

    def send_message(
        self,
        conversation_id: str,
        text: str,
        callbacks: BackendCallbacks,
        on_started: Callable[[RequestContext], None] | None = None,
    ) -> RequestContext:
        backend = self._require_backend()
        if not backend.conversation_exists(conversation_id):
            raise ValueError("unknown conversation_id")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("message text is required")

        context = self.start_request(conversation_id)
        request_id = context.request_id
        if on_started is not None:
            on_started(context)

        callback_lock = threading.Lock()
        callback_ready = False
        pending_callbacks: list[tuple[Callable, tuple]] = []

        def dispatch(function: Callable, *args) -> None:
            nonlocal callback_ready
            with callback_lock:
                if not callback_ready:
                    pending_callbacks.append((function, args))
                    return
            function(*args)

        wrapped = BackendCallbacks(
            on_text_delta=lambda delta: dispatch(callbacks.on_text_delta, delta),
            on_tool_event=lambda event: dispatch(self._publish_backend_tool_event, request_id, event, callbacks),
            on_done=lambda: dispatch(self._backend_done, request_id, callbacks),
            on_error=lambda error: dispatch(self._backend_error, request_id, error, callbacks),
        )
        try:
            handle = backend.send_message(conversation_id, text, wrapped)
        except Exception as exc:
            self.fail_request(request_id, str(exc))
            raise

        self._execution_handles[request_id] = handle
        with callback_lock:
            callback_ready = True
            queued = list(pending_callbacks)
            pending_callbacks.clear()
        for function, args in queued:
            function(*args)

        if self.requests.get(request_id).terminal:
            self._execution_handles.pop(request_id, None)
        return context

    def _publish_backend_tool_event(self, request_id: str, event: dict, callbacks: BackendCallbacks) -> None:
        event_type = event.get("type")
        request = self.requests.get(request_id)
        if event_type == "tool_interaction":
            normalized = self.publish_legacy_tool_request(request_id, event)
        elif event_type == "tool_result":
            normalized = self.tool_bridge.publish_result(request, event)
            normalized["conversation_id"] = self.get_context(request_id).conversation_id
        else:
            raise ValueError(f"unsupported backend tool event: {event_type}")
        callbacks.on_tool_event(normalized)

    def _backend_done(self, request_id: str, callbacks: BackendCallbacks) -> None:
        request = self.requests.get(request_id)
        if request.state is RequestState.CANCEL_REQUESTED:
            self.acknowledge_cancelled(request_id)
        elif not request.terminal:
            self.complete_request(request_id)
        callbacks.on_done()

    def _backend_error(self, request_id: str, error: str, callbacks: BackendCallbacks) -> None:
        request = self.requests.get(request_id)
        if not request.terminal:
            self.fail_request(request_id, error)
        callbacks.on_error(error)

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
        if self.backend is not None:
            try:
                handle = self._execution_handles[request_id]
            except KeyError as exc:
                raise ValueError("request has no backend execution handle") from exc
            self.backend.choose_tool_option(handle, legacy_index)
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
        self._execution_handles.pop(request_id, None)

    def fail_request(self, request_id: str, error: str) -> None:
        self.requests.get(request_id).fail(error)
        self._execution_handles.pop(request_id, None)

    def cancel_request(self, request_id: str) -> bool:
        request = self.requests.get(request_id)
        if request.terminal:
            return False
        request.request_cancel()
        self.tool_bridge.cancel(request)
        if self.backend is not None:
            handle = self._execution_handles.get(request_id)
            if handle is not None:
                self.backend.cancel(handle)
        return True

    def acknowledge_cancelled(self, request_id: str) -> str:
        request = self.requests.get(request_id)
        request.mark_cancelled()
        self._execution_handles.pop(request_id, None)
        return request.cancellation_summary()
