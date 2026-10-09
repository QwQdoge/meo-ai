from __future__ import annotations

import unittest

from meo.cloud.relay import RelayRegistry, RelaySession


class FakeConnection:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


class RelayRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_requires_owned_online_device_and_capability(self) -> None:
        registry = RelayRegistry()
        connection = FakeConnection()
        registry.register(
            RelaySession(
                account_user_id="user-1",
                device_id="legion",
                capabilities=("agent.chat", "agent.workspace"),
            ),
            connection,
        )

        await registry.dispatch_agent_run(
            account_user_id="user-1",
            device_id="legion",
            run_id="run-1",
            conversation_id="conversation-1",
            text="Check the repository",
        )

        self.assertEqual(connection.sent[0]["type"], "dispatch")
        self.assertEqual(connection.sent[0]["protocol_version"], 1)
        self.assertEqual(connection.sent[0]["device_id"], "legion")

    async def test_cross_account_dispatch_is_rejected(self) -> None:
        registry = RelayRegistry()
        registry.register(
            RelaySession("user-1", "legion", ("agent.chat",)),
            FakeConnection(),
        )
        with self.assertRaises(PermissionError):
            await registry.dispatch_agent_run(
                account_user_id="user-2",
                device_id="legion",
                run_id="run-1",
                conversation_id="conversation-1",
                text="Do something",
            )

    async def test_missing_capability_is_rejected(self) -> None:
        registry = RelayRegistry()
        registry.register(
            RelaySession("user-1", "legion", ("files.read",)),
            FakeConnection(),
        )
        with self.assertRaises(PermissionError):
            await registry.dispatch_agent_run(
                account_user_id="user-1",
                device_id="legion",
                run_id="run-1",
                conversation_id="conversation-1",
                text="Do something",
            )

    async def test_unregister_only_removes_matching_connection(self) -> None:
        registry = RelayRegistry()
        first = FakeConnection()
        second = FakeConnection()
        session = RelaySession("user-1", "legion", ("agent.chat",))
        registry.register(session, first)
        registry.register(session, second)

        registry.unregister("legion", first)
        self.assertTrue(registry.is_online("user-1", "legion"))
        registry.unregister("legion", second)
        self.assertFalse(registry.is_online("user-1", "legion"))

    async def test_cancel_and_decision_are_owner_scoped(self) -> None:
        registry = RelayRegistry()
        connection = FakeConnection()
        registry.register(
            RelaySession("user-1", "legion", ("agent.chat",)),
            connection,
        )
        await registry.cancel_agent_run(
            account_user_id="user-1", device_id="legion", run_id="run-1"
        )
        await registry.submit_decision(
            account_user_id="user-1",
            device_id="legion",
            run_id="run-1",
            decision_id="decision-1",
            option_index=0,
        )
        self.assertEqual([item["type"] for item in connection.sent], ["cancel", "decision"])


if __name__ == "__main__":
    unittest.main()
