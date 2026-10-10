from __future__ import annotations

import unittest

from meo.device.executor import AgentServiceExecutor
from meo.device.protocol import AgentRunBinding, AgentRunStatus
from meo.device.workspace_bridge import local_conversation_id


class FakeController:
    def __init__(self) -> None:
        self.workspaces = {
            "default": {"path": "/home/user"},
            "workspace-meo-ai": {"path": "/home/user/Projects/meo-ai"},
        }
        self.chats = {1: {"workspace_id": "default"}}

    def move_chat_to_workspace(self, chat_id: int, workspace_id: str) -> None:
        self.chats[chat_id]["workspace_id"] = workspace_id


class FakeBackend:
    def __init__(self) -> None:
        self.controller = FakeController()
        self._conversations: dict[str, int] = {}

    def conversation_exists(self, conversation_id: str) -> bool:
        return conversation_id in self._conversations

    def attach_existing_session(self, conversation_id: str) -> int:
        self._conversations[conversation_id] = 1
        return 1


class FakeContext:
    request_id = "request-1"


class FakeService:
    def __init__(self) -> None:
        self.backend = FakeBackend()
        self.sent: list[tuple[str, str]] = []

    def send_message(self, conversation_id, text, callbacks, on_started=None):
        self.sent.append((conversation_id, text))
        if on_started is not None:
            on_started(FakeContext())
        callbacks.on_text_delta("ok")
        callbacks.on_done()

    def cancel_request(self, request_id):
        pass

    def choose_tool_option(self, request_id, decision_id, option_index):
        pass


class AgentServiceExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_cloud_conversation_uses_local_alias_and_workspace_id(self) -> None:
        service = FakeService()
        events: list[tuple[str, dict]] = []
        executor = AgentServiceExecutor(
            service=service,  # type: ignore[arg-type]
            publish_event=lambda run_id, event: events.append((run_id, event)),
        )
        run = AgentRunBinding(
            "run-1",
            "550e8400-e29b-41d4-a716-446655440000",
            "legion",
            status=AgentRunStatus.DISPATCHING,
        )

        await executor.dispatch(
            run,
            {
                "text": "Check the repository",
                "workspace_ref": "workspace-meo-ai",
            },
        )

        expected = local_conversation_id(run.conversation_id)
        self.assertEqual(service.sent, [(expected, "Check the repository")])
        self.assertNotEqual(expected, run.conversation_id)
        self.assertEqual(
            service.backend.controller.chats[1]["workspace_id"],
            "workspace-meo-ai",
        )
        self.assertEqual(run.local_request_id, "request-1")
        self.assertEqual(run.status, AgentRunStatus.COMPLETED)
        self.assertTrue(any(event[1]["type"] == "text_delta" for event in events))

    async def test_unknown_workspace_rejects_before_agent_execution(self) -> None:
        service = FakeService()
        executor = AgentServiceExecutor(
            service=service,  # type: ignore[arg-type]
            publish_event=lambda _run_id, _event: None,
        )
        run = AgentRunBinding(
            "run-1",
            "conversation-1",
            "legion",
            status=AgentRunStatus.DISPATCHING,
        )
        with self.assertRaises(ValueError):
            await executor.dispatch(
                run,
                {"text": "Check", "workspace_ref": "unknown-workspace"},
            )
        self.assertEqual(service.sent, [])


if __name__ == "__main__":
    unittest.main()
