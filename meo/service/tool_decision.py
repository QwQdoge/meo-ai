from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, Tuple
from uuid import uuid4

from .request_state import RequestLifecycle, RequestState


class DecisionState(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    INVALIDATED = "invalidated"


@dataclass
class ToolDecision:
    decision_id: str
    request_id: str
    options: Tuple[str, ...]
    state: DecisionState = DecisionState.OPEN
    selected_index: int | None = None

    def resolve(self, option_index: int) -> str:
        if self.state is not DecisionState.OPEN:
            raise ValueError(f"decision {self.decision_id} is not open: {self.state}")
        if option_index < 0 or option_index >= len(self.options):
            raise ValueError("tool option index out of range")
        self.selected_index = option_index
        self.state = DecisionState.RESOLVED
        return self.options[option_index]

    def invalidate(self) -> None:
        if self.state is DecisionState.OPEN:
            self.state = DecisionState.INVALIDATED


class ToolDecisionRegistry:
    """Own service-issued decision identities and reject stale/mismatched replies."""

    def __init__(self) -> None:
        self._decisions: Dict[str, ToolDecision] = {}
        self._current_for_request: Dict[str, str] = {}

    def issue(self, request: RequestLifecycle, options: Iterable[str]) -> ToolDecision:
        if request.state is not RequestState.AWAITING_TOOL:
            raise ValueError("tool decisions can only be issued while awaiting_tool")
        if not request.may_start_new_work:
            raise ValueError("cancelled/cancelling request cannot issue a decision")
        normalized = tuple(str(option) for option in options)
        if not normalized:
            raise ValueError("tool decision requires at least one option")

        previous_id = self._current_for_request.get(request.request_id)
        if previous_id is not None:
            self._decisions[previous_id].invalidate()

        decision = ToolDecision(
            decision_id=f"decision:{uuid4()}",
            request_id=request.request_id,
            options=normalized,
        )
        self._decisions[decision.decision_id] = decision
        self._current_for_request[request.request_id] = decision.decision_id
        return decision

    def resolve(self, request: RequestLifecycle, decision_id: str, option_index: int) -> str:
        decision = self._decisions.get(decision_id)
        if decision is None:
            raise ValueError("unknown decision_id")
        if decision.request_id != request.request_id:
            raise ValueError("decision_id does not belong to request")
        if self._current_for_request.get(request.request_id) != decision_id:
            raise ValueError("stale decision_id")
        if request.state is not RequestState.AWAITING_TOOL:
            raise ValueError("request is not awaiting a tool decision")
        selected = decision.resolve(option_index)
        self._current_for_request.pop(request.request_id, None)
        return selected

    def invalidate_for_request(self, request_id: str) -> str | None:
        decision_id = self._current_for_request.pop(request_id, None)
        if decision_id is not None:
            self._decisions[decision_id].invalidate()
        return decision_id
