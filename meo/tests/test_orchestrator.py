from __future__ import annotations

import unittest

from meo.cloud.orchestrator import (
    AgentRunOrchestrator,
    AgentRunRequest,
    ResolvedDevice,
)
from meo.cloud.policy import PermissionMode
from meo.cloud.relay import RelayRegistry, RelaySession


class FakeConnection:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


class FakeStore:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.updated: list[dict] = []

    async def create_agent_run(self, **values) -> None:
        self.created.append(values)

    async def update_agent_run(self, **values) -> None:
        self.updated.append(values)


class FakeResolver:
    def __init__(self, resolved: ResolvedDevice) -> None:
        self.resolved = resolved

    async def resolve(self, **_kwargs) -> ResolvedDevice:
        return self.resolved


class AgentRunOrchestratorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.store = FakeStore()
        self.connection = FakeConnection()
        self.relay = RelayRegistry()
        self.relay.register(
            RelaySession("user-1", "legion", ("agent.chat",)),
            self.connection,
        )
        self.resolver = FakeResolver(ResolvedDevice("legion", "workspace-meo-ai"))
        self.orchestrator = AgentRunOrchestrator(
            store=self.store,
            relay=self.relay,
            resolver=self.resolver,
        )

    async def test_server_routed_workspace_is_persisted_and_dispatched(self) -> None:
        created = await self.orchestrator.create_and_dispatch(
            user_id="user-1",
            request=AgentRunRequest(
                conversation_id="conversation-1",
                text="Check the repository",
                project_id="project-1",
            ),
        )
        self.assertEqual(created.device_id, "legion")
        self.assertEqual(self.store.created[0]["workspace_ref"], "workspace-meo-ai")
        self.assertEqual(self.store.created[0]["permission_mode"], "smart")
        self.assertEqual(self.connection.sent[0]["workspace_ref"], "workspace-meo-ai")
        self.assertNotIn("/home/", self.connection.sent[0]["workspace_ref"])
        self.assertEqual(self.store.updated[-1]["values"]["status"], "dispatching")

    async def test_full_access_requires_server_side_trust(self) -> None:
        with self.assertRaises(PermissionError):
            await self.orchestrator.create_and_dispatch(
                user_id="user-1",
                request=AgentRunRequest(
                    conversation_id="conversation-1",
                    text="Check the repository",
                    permission_mode=PermissionMode.FULL_ACCESS,
                ),
            )
        self.assertEqual(self.store.created, [])
        self.assertEqual(self.connection.sent, [])

    async def test_full_access_can_be_used_after_trusted_authorization(self) -> None:
        created = await self.orchestrator.create_and_dispatch(
            user_id="user-1",
            request=AgentRunRequest(
                conversation_id="conversation-1",
                text="Check the repository",
                permission_mode=PermissionMode.FULL_ACCESS,
            ),
            allow_full_access=True,
        )
        self.assertEqual(created.permission_mode, PermissionMode.FULL_ACCESS)
        self.assertEqual(self.store.created[0]["permission_mode"], "full_access")


if __name__ == "__main__":
    unittest.main()
