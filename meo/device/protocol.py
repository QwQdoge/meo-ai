from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional


class AgentRunStatus(str, Enum):
    QUEUED = "queued"
    DISPATCHING = "dispatching"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    CANCEL_REQUESTED = "cancel_requested"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


_TERMINAL_RUN_STATES = {
    AgentRunStatus.COMPLETED,
    AgentRunStatus.CANCELLED,
    AgentRunStatus.FAILED,
}

_ALLOWED_RUN_TRANSITIONS = {
    AgentRunStatus.QUEUED: {
        AgentRunStatus.DISPATCHING,
        AgentRunStatus.CANCEL_REQUESTED,
        AgentRunStatus.CANCELLED,
        AgentRunStatus.FAILED,
    },
    AgentRunStatus.DISPATCHING: {
        AgentRunStatus.RUNNING,
        AgentRunStatus.CANCEL_REQUESTED,
        AgentRunStatus.FAILED,
    },
    AgentRunStatus.RUNNING: {
        AgentRunStatus.AWAITING_APPROVAL,
        AgentRunStatus.COMPLETED,
        AgentRunStatus.CANCEL_REQUESTED,
        AgentRunStatus.FAILED,
    },
    AgentRunStatus.AWAITING_APPROVAL: {
        AgentRunStatus.RUNNING,
        AgentRunStatus.CANCEL_REQUESTED,
        AgentRunStatus.FAILED,
    },
    AgentRunStatus.CANCEL_REQUESTED: {
        AgentRunStatus.CANCELLED,
        AgentRunStatus.FAILED,
    },
}


@dataclass(frozen=True)
class DeviceRegistration:
    device_id: str
    display_name: str
    capabilities: tuple[str, ...]

    @classmethod
    def create(
        cls,
        device_id: str,
        display_name: str,
        capabilities: Iterable[str],
    ) -> "DeviceRegistration":
        normalized = tuple(str(item).strip() for item in capabilities)
        registration = cls(
            device_id=str(device_id).strip(),
            display_name=str(display_name).strip(),
            capabilities=normalized,
        )
        registration.validate()
        return registration

    def validate(self) -> None:
        if not self.device_id:
            raise ValueError("device_id is required")
        if not self.display_name:
            raise ValueError("display_name is required")
        if any(not item for item in self.capabilities):
            raise ValueError("capability IDs must be non-empty")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("capability IDs must be unique")


@dataclass
class AgentRunBinding:
    """Cloud-side identity mapped to exactly one local AgentService request.

    Network reconnect may resume an existing binding, but it must never replace
    `local_request_id` with a new request and accidentally replay side effects.
    """

    run_id: str
    conversation_id: str
    device_id: str
    status: AgentRunStatus = AgentRunStatus.QUEUED
    local_request_id: Optional[str] = None
    last_event_seq: int = -1

    def __post_init__(self) -> None:
        for field_name in ("run_id", "conversation_id", "device_id"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")
        if self.last_event_seq < -1:
            raise ValueError("last_event_seq must be -1 or greater")

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL_RUN_STATES

    def transition(self, next_status: AgentRunStatus) -> None:
        if self.terminal:
            raise ValueError(f"AgentRun is already terminal: {self.status}")
        if next_status not in _ALLOWED_RUN_TRANSITIONS.get(self.status, set()):
            raise ValueError(f"invalid AgentRun transition {self.status} -> {next_status}")
        self.status = next_status

    def bind_local_request(self, request_id: str) -> None:
        request_id = str(request_id).strip()
        if not request_id:
            raise ValueError("request_id is required")
        if self.local_request_id is None:
            self.local_request_id = request_id
            return
        if self.local_request_id != request_id:
            raise ValueError("AgentRun is already bound to a different local request")

    def observe_event(self, seq: int) -> bool:
        """Record a newer local event sequence.

        Returns False for duplicate/stale events so reconnect can be idempotent.
        Sequence gaps are not silently repaired here; the caller can request a
        replay from AgentService using its existing reconnect cursor.
        """

        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
            raise ValueError("event seq must be a non-negative integer")
        if seq <= self.last_event_seq:
            return False
        self.last_event_seq = seq
        return True

    def require_local_request(self) -> str:
        if self.local_request_id is None:
            raise ValueError("AgentRun has not been bound to a local request")
        return self.local_request_id
