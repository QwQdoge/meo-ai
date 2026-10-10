from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from meo.device.protocol import AgentRunBinding, AgentRunStatus
from meo.device.workspace_bridge import (
    bind_conversation_workspace,
    ensure_remote_conversation,
)
from meo.service.backend_adapter import BackendCallbacks
from meo.service.core import AgentServiceCore


@dataclass
class AgentServiceExecutor:
    """Adapter from remote AgentRun messages to the existing AgentServiceCore.

    Cloud conversation IDs are mapped to deterministic local Meo conversation
    aliases. Optional workspace references are opaque local workspace IDs and are
    resolved only by the local backend; they are never treated as paths.
    """

    service: AgentServiceCore
    publish_event: Callable[[str, dict], None]

    async def dispatch(self, run: AgentRunBinding, payload: dict) -> None:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("dispatch text is required")

        backend = self.service.backend
        if backend is None:
            raise RuntimeError("AgentService backend is unavailable")

        local_conversation_id = ensure_remote_conversation(
            backend,
            run.conversation_id,
        )
        workspace_ref = payload.get("workspace_ref")
        if workspace_ref is not None:
            if not isinstance(workspace_ref, str) or not workspace_ref.strip():
                raise ValueError("workspace_ref must be a non-empty opaque ID")
            bind_conversation_workspace(
                backend,
                local_conversation_id,
                workspace_ref.strip(),
            )

        def emit(kind: str, body: dict) -> None:
            self.publish_event(run.run_id, {"type": kind, **body})

        def on_started(context) -> None:
            run.bind_local_request(context.request_id)
            if run.status is AgentRunStatus.DISPATCHING:
                run.transition(AgentRunStatus.RUNNING)
            emit("request_started", {"request_id": context.request_id})

        def on_text_delta(delta: str) -> None:
            emit("text_delta", {"text": delta})

        def on_tool_event(event: dict) -> None:
            event_type = event.get("type")
            if event_type == "tool_interaction":
                if run.status is AgentRunStatus.RUNNING:
                    run.transition(AgentRunStatus.AWAITING_APPROVAL)
            elif event_type == "tool_result":
                if run.status is AgentRunStatus.AWAITING_APPROVAL:
                    run.transition(AgentRunStatus.RUNNING)
            emit("tool_event", {"event": event})

        def on_done() -> None:
            if not run.terminal:
                if run.status is AgentRunStatus.CANCEL_REQUESTED:
                    run.transition(AgentRunStatus.CANCELLED)
                else:
                    run.transition(AgentRunStatus.COMPLETED)
            emit("done", {"status": run.status.value})

        def on_error(_error: str) -> None:
            if not run.terminal:
                run.transition(AgentRunStatus.FAILED)
            emit("error", {"message": "Agent request failed", "status": run.status.value})

        callbacks = BackendCallbacks(
            on_text_delta=on_text_delta,
            on_tool_event=on_tool_event,
            on_done=on_done,
            on_error=on_error,
        )
        self.service.send_message(
            local_conversation_id,
            text.strip(),
            callbacks,
            on_started=on_started,
        )

    async def cancel(self, run: AgentRunBinding) -> None:
        request_id = run.require_local_request()
        self.service.cancel_request(request_id)

    async def decide(self, run: AgentRunBinding, decision_id: str, option_index: int) -> None:
        request_id = run.require_local_request()
        self.service.choose_tool_option(request_id, decision_id, option_index)
