from __future__ import annotations

import unittest

from meo.device.agentd import AgentdConfig, MeoAgentd
from meo.device.protocol import AgentRunStatus, DeviceRegistration


class FakeConnection:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def receive_json(self) -> dict:
        raise RuntimeError("not used")

    async def close(self) -> None:
        pass


class FakeExecutor:
    def __init__(self) -> None:
        self.dispatched: list[str] = []
        self.cancelled: list[str] = []
        self.decisions: list[tuple[str, str, int]] = []

    async def dispatch(self, run, payload: dict) -> None:
        self.dispatched.append(run.run_id)
        run.bind_local_request(f"local-{run.run_id}")
        run.transition(AgentRunStatus.RUNNING)

    async def cancel(self, run) -> None:
        self.cancelled.append(run.run_id)

    async def decide(self, run, decision_id: str, option_index: int) -> None:
        self.decisions.append((run.run_id, decision_id, option_index))


async def unused_connector(_config):
    raise RuntimeError("not used")


class AgentdTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        device = DeviceRegistration.create(
            "legion",
            "Legion Y9000X",
            ["agent.chat", "agent.workspace"],
        )
        self.config = AgentdConfig(
            device=device,
            relay_url="wss://relay.example.test/v1/device",
            device_token="device-token",
        )
        self.executor = FakeExecutor()
        self.agentd = MeoAgentd(self.config, unused_connector, self.executor)
        self.connection = FakeConnection()

    async def test_duplicate_dispatch_is_acknowledged_without_reexecution(self) -> None:
        message = {
            "type": "dispatch",
            "run_id": "run-1",
            "conversation_id": "conversation-1",
            "device_id": "legion",
            "text": "Check the repository",
        }
        await self.agentd.handle_message(self.connection, message)
        await self.agentd.handle_message(self.connection, message)

        self.assertEqual(self.executor.dispatched, ["run-1"])
        self.assertFalse(self.connection.sent[0]["reused"])
        self.assertTrue(self.connection.sent[1]["reused"])

    async def test_cancel_delegates_to_existing_local_request(self) -> None:
        await self.agentd.handle_message(
            self.connection,
            {
                "type": "dispatch",
                "run_id": "run-2",
                "conversation_id": "conversation-1",
                "device_id": "legion",
                "text": "Run tests",
            },
        )
        await self.agentd.handle_message(
            self.connection,
            {"type": "cancel", "run_id": "run-2"},
        )

        self.assertEqual(self.executor.cancelled, ["run-2"])
        self.assertEqual(
            self.agentd.runs["run-2"].status,
            AgentRunStatus.CANCEL_REQUESTED,
        )

    async def test_decision_requires_approval_state(self) -> None:
        await self.agentd.handle_message(
            self.connection,
            {
                "type": "dispatch",
                "run_id": "run-3",
                "conversation_id": "conversation-1",
                "device_id": "legion",
                "text": "Use a tool",
            },
        )
        run = self.agentd.runs["run-3"]
        run.transition(AgentRunStatus.AWAITING_APPROVAL)

        await self.agentd.handle_message(
            self.connection,
            {
                "type": "decision",
                "run_id": "run-3",
                "decision_id": "decision-1",
                "option_index": 0,
            },
        )

        self.assertEqual(
            self.executor.decisions,
            [("run-3", "decision-1", 0)],
        )
        self.assertEqual(run.status, AgentRunStatus.RUNNING)

    async def test_dispatch_for_other_device_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            await self.agentd.handle_message(
                self.connection,
                {
                    "type": "dispatch",
                    "run_id": "run-x",
                    "conversation_id": "conversation-1",
                    "device_id": "other-device",
                    "text": "Do something",
                },
            )


if __name__ == "__main__":
    unittest.main()
