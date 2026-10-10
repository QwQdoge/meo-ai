from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol, runtime_checkable


MEMORY_SCOPES = {"account", "device", "workspace", "conversation"}
MEMORY_STATES = {"active", "disabled", "deleted"}
SYNC_STATES = {"local", "pending", "synced", "conflict", "error"}


def _required(value: str, field: str, *, limit: int = 65536) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    if len(value) > limit:
        raise ValueError(f"{field} is too long")
    return value


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    text: str
    scope: str
    source: str
    created_at: str
    updated_at: str = ""
    state: str = "active"
    pinned: bool = False
    sync_state: str = "local"
    workspace_id: str = ""
    conversation_id: str = ""

    def __post_init__(self) -> None:
        _required(self.memory_id, "memory_id", limit=256)
        _required(self.text, "text")
        _required(self.source, "source", limit=512)
        _required(self.created_at, "created_at", limit=128)
        if self.scope not in MEMORY_SCOPES:
            raise ValueError("unsupported memory scope")
        if self.state not in MEMORY_STATES:
            raise ValueError("unsupported memory state")
        if self.sync_state not in SYNC_STATES:
            raise ValueError("unsupported memory sync state")

    def public_dict(self) -> dict:
        return {
            "memory_id": self.memory_id,
            "text": self.text,
            "scope": self.scope,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "state": self.state,
            "pinned": self.pinned,
            "sync_state": self.sync_state,
            "workspace_id": self.workspace_id,
            "conversation_id": self.conversation_id,
        }


@runtime_checkable
class MemoryBackend(Protocol):
    """Optional native memory ownership contract.

    Memory is separate from transcript history. Implementations own persistence
    and deletion; a model cannot declare a memory deleted by writing prose.
    """

    def list_memories(self, *, scope: str | None = None, query: str = "") -> Iterable[MemoryRecord]: ...
    def set_memory_enabled(self, enabled: bool) -> bool: ...
    def memory_enabled(self) -> bool: ...
    def update_memory(self, memory_id: str, *, text: str | None = None, pinned: bool | None = None) -> MemoryRecord: ...
    def delete_memory(self, memory_id: str) -> None: ...
