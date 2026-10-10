from __future__ import annotations

import unittest

from meo.cloud.api import AgentRunApi, ApiError
from meo.cloud.orchestrator import AgentRunCreated
from meo.cloud.policy import PermissionMode
from meo.cloud.relay import RelayRegistry, RelaySession


class FakeConnection:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


class FakeStore:
    def __init__(self) -> None:
        self.run = {"id": "run-1", "device_id": "legion", "status": "running"}
        self.updated: list[dict] = []

    async def get_agent_run(self, *, user_id: str, run_id: str):
        if user_id != "user-1" or run_id != "run-1":
            return None
        return dict(self.run)

    async def update_agent_run(self, **values) -> None:
        self.updated.append(values)


class FakeOrchestrator:
    def __init__(self) -> None:
        self.requests = []

    async def create_and_dispatch(self, *, user_id, request, allow_full_access=False):
        self.requests.append((user_id, request, allow_full_access))
        if request.permission_mode is PermissionMode.FULL_ACCESS and not allow_full_access:
            raise PermissionError("not trusted")
        return AgentRunCreated(
            run_id="run-new",
            device_id="legion",
            status="dispatching",
            permission_mode=request.permission_mode,
        )


class AgentRunApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.store = FakeStore()
        self.connection = FakeConnection()
        self.relay = RelayRegistry()
        self.relay.register(
            RelaySession("user-1", "legion", ("agent.chat",)),
            self.connection,
        )
        self.orchestrator = FakeOrchestrator()
        self.api = AgentRunApi(
            store=self.store,
            relay=self.relay,
            orchestrator=self.orchestrator,
        )

    async def test_minimal_request_is_enough(self) -> None:
        result = await self.api.create(
            user_id="user-1",
            payload={
                "conversation_id": "conversation-1",
                "text": "Check my project",
            },
        )
        self.assertEqual(result["status"], "dispatching")
        self.assertEqual(result["permission_mode"], "smart")
        request = self.orchestrator.requests[0][1]
        self.assertIsNone(request.project_id)
        self.assertIsNone(request.preferred_device_id)

    async def test_browser_cannot_supply_workspace_or_shell_fields(self) -> None:
        for forbidden in ("workspace_ref", "command", "shell", "device_token"):
            with self.subTest(forbidden=forbidden):
                with self.assertRaises(ApiError) as raised:
                    await self.api.create(
                        user_id="user-1",
                        payload={
                            "conversation_id": "conversation-1",
                            "text": "Check my project",
                            forbidden: "unsafe",
                        },
                    )
                self.assertEqual(raised.exception.code, "unsupported_fields")

    async def test_full_access_cannot_be_enabled_only_by_browser_payload(self) -> None:
        with self.assertRaises(ApiError) as raised:
            await self.api.create(
                user_id="user-1",
                payload={
                    "conversation_id": "conversation-1",
                    "text": "Do work",
                    "permission_mode": "full_access",
                },
            )
        self.assertEqual(raised.exception.code, "full_access_not_authorized")
        self.assertEqual(raised.exception.status, 403)

    async def test_cross_account_run_is_indistinguishable_from_missing(self) -> None:
        with self.assertRaises(ApiError) as raised:
            await self.api.cancel(user_id="other-user", run_id="run-1")
        self.assertEqual(raised.exception.code, "run_not_found")
        self.assertEqual(raised.exception.status, 404)

    async def test_cancel_is_sent_only_after_owned_run_lookup(self) -> None:
        result = await self.api.cancel(user_id="user-1", run_id="run-1")
        self.assertEqual(result["status"], "cancel_requested")
        self.assertEqual(self.connection.sent[-1]["type"], "cancel")
        self.assertEqual(self.store.updated[-1]["values"]["status"], "cancel_requested")

    async def test_decision_requires_run_to_be_waiting(self) -> None:
        with self.assertRaises(ApiError) as raised:
            await self.api.decide(
                user_id="user-1",
                run_id="run-1",
                decision_id="decision-1",
                option_index=0,
            )
        self.assertEqual(raised.exception.code, "approval_not_pending")


if __name__ == "__main__":
    unittest.main()
