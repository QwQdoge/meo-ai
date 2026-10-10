from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable


SYNC_CATEGORIES = {
    "conversation",
    "conversation_block",
    "resource",
    "artifact",
    "workspace",
    "model_preference",
    "model_role",
    "memory",
    "skill",
    "mcp_metadata",
    "tool_policy",
    "ui_preference",
    "usage_history",
}
SYNC_STATES = {"local", "pending", "synced", "conflict", "error", "deleted"}
_MAX_PAYLOAD_BYTES = 8 * 1024 * 1024
_SENSITIVE_PARTS = {
    "authorization",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "cookie",
    "private_key",
}


class SyncContractError(ValueError):
    pass


def _sensitive_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_PARTS)


def sanitize_sync_payload(value: Any, *, depth: int = 0) -> Any:
    """Return sync-safe JSON data and fail closed on credential-shaped keys."""

    if depth > 10:
        raise SyncContractError("sync payload nesting is too deep")
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        if len(value) > 1024:
            raise SyncContractError("sync payload object has too many fields")
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if _sensitive_key(key):
                raise SyncContractError(f"sync payload contains credential-shaped field: {key}")
            result[key] = sanitize_sync_payload(raw_value, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        if len(value) > 4096:
            raise SyncContractError("sync payload array is too large")
        return [sanitize_sync_payload(item, depth=depth + 1) for item in value]
    raise SyncContractError("sync payload must be JSON compatible")


@dataclass(frozen=True)
class SyncObject:
    object_id: str
    category: str
    revision: int
    updated_at: str
    payload: Mapping[str, Any]
    deleted: bool = False
    state: str = "pending"
    device_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.object_id, str) or not self.object_id.strip() or len(self.object_id) > 512:
            raise SyncContractError("object_id is required")
        if self.category not in SYNC_CATEGORIES:
            raise SyncContractError("unsupported sync category")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 1:
            raise SyncContractError("revision must be a positive integer")
        if not isinstance(self.updated_at, str) or not self.updated_at or len(self.updated_at) > 128:
            raise SyncContractError("updated_at is required")
        if self.state not in SYNC_STATES:
            raise SyncContractError("unsupported sync state")
        safe = sanitize_sync_payload(self.payload)
        encoded = json.dumps(safe, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > _MAX_PAYLOAD_BYTES:
            raise SyncContractError("sync payload is too large")

    def public_dict(self) -> dict:
        return {
            "object_id": self.object_id,
            "category": self.category,
            "revision": self.revision,
            "updated_at": self.updated_at,
            "payload": sanitize_sync_payload(self.payload),
            "deleted": self.deleted,
            "state": self.state,
            "device_id": self.device_id,
        }


@dataclass(frozen=True)
class SyncCursor:
    cursor: str = ""
    has_more: bool = False


@runtime_checkable
class SyncBackend(Protocol):
    """Account/cloud sync boundary; credentials live outside these payloads."""

    def push(self, objects: Iterable[SyncObject]) -> Iterable[SyncObject]: ...
    def pull(self, cursor: str = "") -> tuple[Iterable[SyncObject], SyncCursor]: ...


def resolve_revision(local: SyncObject, remote: SyncObject) -> str:
    """Return an explicit merge disposition; never silently overwrite conflicts."""

    if local.object_id != remote.object_id or local.category != remote.category:
        raise SyncContractError("cannot compare unrelated sync objects")
    if local.revision > remote.revision:
        return "use_local"
    if remote.revision > local.revision:
        return "use_remote"
    if local.public_dict() == remote.public_dict():
        return "same"
    return "conflict"
