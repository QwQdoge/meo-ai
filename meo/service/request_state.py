from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RequestState(str, Enum):
    QUEUED = "queued"
    RUNNING_MODEL = "running_model"
    AWAITING_TOOL = "awaiting_tool"
    RUNNING_TOOL = "running_tool"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


_TERMINAL = {
    RequestState.CANCELLED,
    RequestState.COMPLETED,
    RequestState.FAILED,
}

_ALLOWED = {
    RequestState.QUEUED: {
        RequestState.RUNNING_MODEL,
        RequestState.CANCEL_REQUESTED,
        RequestState.CANCELLED,
        RequestState.FAILED,
    },
    RequestState.RUNNING_MODEL: {
        RequestState.AWAITING_TOOL,
        RequestState.COMPLETED,
        RequestState.CANCEL_REQUESTED,
        RequestState.FAILED,
    },
    RequestState.AWAITING_TOOL: {
        RequestState.RUNNING_TOOL,
        RequestState.RUNNING_MODEL,
        RequestState.CANCEL_REQUESTED,
        RequestState.FAILED,
    },
    RequestState.RUNNING_TOOL: {
        RequestState.RUNNING_MODEL,
        RequestState.COMPLETED,
        RequestState.CANCEL_REQUESTED,
        RequestState.FAILED,
    },
    RequestState.CANCEL_REQUESTED: {
        RequestState.CANCELLED,
        RequestState.FAILED,
    },
}


@dataclass
class RequestLifecycle:
    request_id: str
    state: RequestState = RequestState.QUEUED
    external_effect_committed: bool = False
    error: Optional[str] = None

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL

    @property
    def may_start_new_work(self) -> bool:
        return self.state not in _TERMINAL and self.state is not RequestState.CANCEL_REQUESTED

    def transition(self, next_state: RequestState) -> None:
        if self.terminal:
            raise ValueError(f"request {self.request_id} is already terminal: {self.state}")
        if next_state not in _ALLOWED.get(self.state, set()):
            raise ValueError(f"invalid transition {self.state} -> {next_state}")
        self.state = next_state

    def request_cancel(self) -> None:
        if self.terminal:
            return
        if self.state is RequestState.CANCEL_REQUESTED:
            return
        self.transition(RequestState.CANCEL_REQUESTED)

    def mark_cancelled(self) -> None:
        if self.state is not RequestState.CANCEL_REQUESTED:
            raise ValueError("cancellation must be requested before marking cancelled")
        self.transition(RequestState.CANCELLED)

    def mark_external_effect_committed(self) -> None:
        self.external_effect_committed = True

    def fail(self, error: str) -> None:
        if self.terminal:
            raise ValueError(f"request {self.request_id} is already terminal: {self.state}")
        if self.state is RequestState.CANCEL_REQUESTED:
            self.transition(RequestState.FAILED)
        else:
            self.transition(RequestState.FAILED)
        self.error = error

    def cancellation_summary(self) -> str:
        if self.state is not RequestState.CANCELLED:
            raise ValueError("cancellation summary is only valid for cancelled requests")
        if self.external_effect_committed:
            return (
                "Agent workflow stopped. An external action had already been committed and "
                "may continue under its owning service; cancellation does not roll it back."
            )
        return "Agent workflow stopped before any recorded external effect was committed."
