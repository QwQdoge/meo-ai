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
        if self.backend is None:
            raise RuntimeError("AgentServiceCore has no backend adapter")
        if not self.backend.conversation_exists(conversation_id):
            raise ValueError("unknown conversation_id")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("message text is required")

        context = self.start_request(conversation_id)
        request_id = context.request_id
        if on_started is not None:
            on_started(context)

        # Some backends start worker threads before returning their execution
        # handle. Buffer callbacks until the handle is registered so an immediate
        # tool decision or cancel can never observe a request without its handle.
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
            handle = self.backend.send_message(conversation_id, text, wrapped)
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

        # A buffered completion/error callback may have made the request terminal.
        if self.requests.get(request_id).terminal:
            self._execution_handles.pop(request_id, None)
        return context

    def _publish_backend_tool_event(self, request_id: str, event: dict, callbacks: BackendCallbacks) -> None:
        callbacks.on_tool_event(self.publish_legacy_tool_request(request_id, event))

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
