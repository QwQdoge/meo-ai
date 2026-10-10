from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Protocol, runtime_checkable


@dataclass(frozen=True)
class ModelInfo:
    model_id: str
    label: str
    provider: str = ""
    selection_scope: str = "conversation"
    selected: bool = False


@dataclass(frozen=True)
class SkillInfo:
    skill_id: str
    label: str
    enabled: bool
    configured_enabled: bool | None = None
    selection_scope: str = "profile"
    override_source: str = ""


@dataclass(frozen=True)
class McpServerInfo:
    server_id: str
    label: str
    enabled: bool


@dataclass(frozen=True)
class ConversationMessage:
    role: str
    text: str


@dataclass(frozen=True)
class InputResource:
    """Request-local resource material passed to a capable backend.

    The stable frontend identity is `resource_id`. AgentService resolves that
    identity and supplies bytes internally so adapters never need a user-visible
    filesystem path.
    """

    resource_id: str
    kind: str
    name: str
    mime_type: str
    data: bytes


@dataclass(frozen=True)
class BackendCallbacks:
    on_text_delta: Callable[[str], None]
    on_tool_event: Callable[[dict], None]
    on_done: Callable[[], None]
    on_error: Callable[[str], None]


@runtime_checkable
class ResourceInputBackend(Protocol):
    """Optional extension implemented only when resource input is real."""

    def send_message_with_resources(
        self,
        conversation_id: str,
        text: str,
        resources: tuple[InputResource, ...],
        callbacks: BackendCallbacks,
    ) -> object: ...


@runtime_checkable
class AgentBackendAdapter(Protocol):
    """Narrow runtime interface consumed by AgentService.

    Implementations may wrap the current Newelle controller or a later extracted
    headless core. This module intentionally imports no GTK/Adwaita/WebKit or
    Newelle UI modules.
    """

    def list_conversations(self) -> Iterable[dict]: ...

    def create_conversation(self) -> str: ...

    def conversation_exists(self, conversation_id: str) -> bool: ...

    def list_messages(self, conversation_id: str) -> Iterable[ConversationMessage]: ...

    def send_message(
        self,
        conversation_id: str,
        text: str,
        callbacks: BackendCallbacks,
    ) -> object: ...

    def choose_tool_option(
        self,
        execution_handle: object,
        legacy_option_index: int,
    ) -> None: ...

    def cancel(self, execution_handle: object) -> None: ...

    def list_models(self) -> Iterable[ModelInfo]: ...

    def set_model(self, conversation_id: str, model_id: str) -> None: ...

    def list_skills(self) -> Iterable[SkillInfo]: ...

    def set_skill_enabled(self, skill_id: str, enabled: bool) -> None: ...

    def list_mcp_servers(self) -> Iterable[McpServerInfo]: ...
