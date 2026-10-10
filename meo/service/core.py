from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable, Dict

from .backend_adapter import (
    AgentBackendAdapter,
    BackendCallbacks,
    InputResource,
)
from .content_blocks import legacy_text_block
from .legacy_v2_bridge import LegacyV2ToolBridge
from .model_roles import ModelRoleRegistry
from .presentation import normalize_presentation_card
from .request_registry import RequestRegistry
from .request_state import RequestLifecycle, RequestState
from .resources import ConversationResourceStore
from .response_meta import normalize_response_meta


_MAX_REQUEST_RESOURCES = 16
_MAX_REQUEST_RESOURCE_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    conversation_id: str


class AgentServiceCore:
    def __init__(
        self,
        backend: AgentBackendAdapter | None = None,
        model_roles: ModelRoleRegistry | None = None,
        resource_store: ConversationResourceStore | None = None,
    ) -> None:
        self.backend = backend
        self.model_roles = model_roles or ModelRoleRegistry()
        self.resource_store = resource_store
        self.requests = RequestRegistry()
        self.tool_bridge = LegacyV2ToolBridge()
        self._contexts: Dict[str, RequestContext] = {}
        self._execution_handles: Dict[str, object] = {}

    def _require_backend(self) -> AgentBackendAdapter:
        if self.backend is None:
            raise RuntimeError("AgentServiceCore has no backend adapter")
        return self.backend

    def _require_resource_store(self) -> ConversationResourceStore:
        if self.resource_store is None:
            raise RuntimeError("AgentServiceCore has no resource store")
        return self.resource_store

    def _require_conversation(self, conversation_id: str) -> AgentBackendAdapter:
        backend = self._require_backend()
        if not backend.conversation_exists(conversation_id):
            raise ValueError("unknown conversation_id")
        return backend

    def get_agent_state(self) -> dict:
        return {
            "ready": self.backend is not None,
            "resources_ready": self.resource_store is not None,
            "active_requests": self.requests.active_count(),
            "request_states": self.requests.state_counts(),
        }

    def list_conversations(self) -> list[dict]:
        return list(self._require_backend().list_conversations())

    def create_conversation(self) -> str:
        conversation_id = self._require_backend().create_conversation()
        if not isinstance(conversation_id, str) or not conversation_id:
            raise RuntimeError("backend returned an invalid conversation ID")
        return conversation_id

    def list_messages(self, conversation_id: str) -> list[dict]:
        backend = self._require_conversation(conversation_id)
        messages = []
        for index, item in enumerate(backend.list_messages(conversation_id)):
            if item.role not in {"user", "assistant"}:
                raise RuntimeError("backend returned an invalid conversation role")
            if not isinstance(item.text, str):
                raise RuntimeError("backend returned invalid conversation text")
            block = legacy_text_block(
                block_id=f"history:{index}:text",
                role=item.role,
                text=item.text,
            )
            messages.append({
                "role": item.role,
                "text": item.text,
                "blocks": [block],
            })
        return messages

    def list_resources(self, conversation_id: str) -> list[dict]:
        self._require_conversation(conversation_id)
        return [record.public_dict() for record in self._require_resource_store().list_resources(conversation_id)]

    def create_text_resource(self, conversation_id: str, *, name: str, text: str) -> dict:
        self._require_conversation(conversation_id)
        record = self._require_resource_store().put_text(conversation_id, name=name, text=text)
        return record.public_dict()

    def reserve_resource(
        self,
        conversation_id: str,
        *,
        kind: str,
        name: str,
        mime_type: str,
        size_bytes: int,
    ) -> dict:
        self._require_conversation(conversation_id)
        record = self._require_resource_store().reserve(
            conversation_id,
            kind=kind,
            name=name,
            mime_type=mime_type,
            size_bytes=size_bytes,
        )
        return record.public_dict()

    def upload_resource(self, conversation_id: str, resource_id: str, data: bytes) -> dict:
        self._require_conversation(conversation_id)
        record = self._require_resource_store().finalize_upload(conversation_id, resource_id, data)
        return record.public_dict()

    def resource_upload_limit(self) -> int:
        return self._require_resource_store().max_resource_bytes

    def delete_resource(self, conversation_id: str, resource_id: str) -> None:
        self._require_conversation(conversation_id)
        self._require_resource_store().delete(conversation_id, resource_id)

    def _resolve_input_resources(
        self,
        conversation_id: str,
        resource_ids: tuple[str, ...],
    ) -> tuple[InputResource, ...]:
        if len(resource_ids) > _MAX_REQUEST_RESOURCES:
            raise ValueError(f"at most {_MAX_REQUEST_RESOURCES} resources may be sent with one request")
        if len(set(resource_ids)) != len(resource_ids):
            raise ValueError("resource_ids must not contain duplicates")
        store = self._require_resource_store()
        resolved: list[InputResource] = []
        total_bytes = 0
        for resource_id in resource_ids:
            if not isinstance(resource_id, str) or not resource_id:
                raise ValueError("resource_ids must contain non-empty strings")
            record = store.get(conversation_id, resource_id)
            if record.state != "ready":
                raise ValueError("all input resources must be ready")
            data = store.read_bytes(conversation_id, resource_id)
            total_bytes += len(data)
            if total_bytes > _MAX_REQUEST_RESOURCE_BYTES:
                raise ValueError("combined request resources exceed the input limit")
            resolved.append(InputResource(
                resource_id=record.resource_id,
                kind=record.kind,
                name=record.name,
                mime_type=record.mime_type,
                data=data,
            ))
        return tuple(resolved)

    def list_models(self) -> list[dict]:
        return [
            {
                "model_id": item.model_id,
                "label": item.label,
                "provider": item.provider,
                "selection_scope": item.selection_scope,
                "selected": item.selected,
            }
            for item in self._require_backend().list_models()
        ]

    def set_model(self, conversation_id: str, model_id: str) -> None:
        self._require_conversation(conversation_id).set_model(conversation_id, model_id)

    def list_model_roles(self) -> list[dict]:
        models = list(self._require_backend().list_models())
        return self.model_roles.list_roles(models)

    def set_model_role(self, role_id: str, model_id: str | None) -> dict:
        models = list(self._require_backend().list_models())
        return self.model_roles.set_role(role_id, model_id, models)

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

    def list_controls(self) -> list[dict]:
        method = getattr(self._require_backend(), "list_controls", None)
        if not callable(method):
            return []
        return [item.public_dict() for item in method()]

    def set_control(self, control_id: str, value) -> dict:
        if not isinstance(control_id, str) or not control_id.strip():
            raise ValueError("control_id is required")
        method = getattr(self._require_backend(), "set_control", None)
        if not callable(method):
            raise ValueError("selected backend does not expose AI controls")
        return method(control_id, value).public_dict()

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
        resource_ids: tuple[str, ...] = (),
    ) -> RequestContext:
        backend = self._require_conversation(conversation_id)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("message text is required")
        if not isinstance(resource_ids, tuple):
            raise ValueError("resource_ids must be a tuple")

        resources: tuple[InputResource, ...] = ()
        send_with_resources = getattr(backend, "send_message_with_resources", None)
        if resource_ids:
            if not callable(send_with_resources):
                raise ValueError("selected backend does not support resource inputs")
            resources = self._resolve_input_resources(conversation_id, resource_ids)

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
            if resources:
                handle = send_with_resources(conversation_id, text, resources, wrapped)
            else:
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
        elif event_type == "presentation_card":
            normalized = normalize_presentation_card(event)
            normalized["request_id"] = request_id
            normalized["conversation_id"] = self.get_context(request_id).conversation_id
        elif event_type == "response_meta":
            normalized = normalize_response_meta(event)
            normalized["request_id"] = request_id
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
