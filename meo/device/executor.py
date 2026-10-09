from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from meo.device.protocol import AgentRunBinding, AgentRunStatus
from meo.service.backend_adapter import BackendCallbacks
from meo.service.core import AgentServiceCore


@dataclass
class AgentServiceExecutor:
    """Adapter from remote AgentRun messages to the existing AgentServiceCore."""

    service: AgentServiceCore
    publish_event: Callable[[str, dict], None]

    async def dispatch(self, run: AgentRunBinding, payload: dict) -> None:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("dispatch text is required")

        conversation_id = run.conversation_id
        if not self.service.backend:
            raise RuntimeError("AgentService backend is unavailable")
        if not self.service.backend.conversation_exists(conversation_id):
            raise ValueError("unknown conversation_id")

        loop = asyncio.get_running_loop()
        done = loop.create_future()

        def emit(kind: str, body: dict) -> None:
            self.publish_event(run.run_id, {"type": kind, **body})

        def on_started(context) -> None:
            run.bind_local_request(context.request_id)
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
            if not done.done():
                done.set_result(None)
            emit("done", {"status": run.status.value})

        def on_error(error: str) -> None:
            if not run.terminal:
                run.transition(AgentRunStatus.FAILED)
            if not done.done():
                done.set_result(None)
            emit("error", {"message": "Agent request failed", "status": run.status.value})

        callbacks = BackendCallbacks(
            on_text_delta=on_text_delta,
            on_tool_event=on_tool_event,
            on_done=on_done,
            on_error=on_error,
        )
        self.service.send_message(
            conversation_id,
            text,
            callbacks,
            on_started=on_started,
        )

    async def cancel(self, run: AgentRunBinding) -> None:
        request_id = run.require_local_request()
        self.service.cancel_request(request_id)

    async def decide(self, run: AgentRunBinding, decision_id: str, option_index: int) -> None:
        request_id = run.require_local_request()
        self.service.choose_tool_option(request_id, decision_id, option_index)
