from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timedelta, timezone
import unittest

from meo.cloud.enrollment import DeviceCredentialClaims
from meo.cloud.relay import RelayRegistry
from meo.cloud.ws_server import RelayWebSocketServer


class FakeVerifier:
    def __init__(self, claims: DeviceCredentialClaims) -> None:
        self.claims = claims
        self.tokens: list[str] = []

    async def verify(self, bearer_token: str) -> DeviceCredentialClaims:
        self.tokens.append(bearer_token)
        return self.claims


class FakeStore:
    def __init__(self, *, inserted: bool = True) -> None:
        self.inserted = inserted
        self.devices: list[dict] = []
        self.events: list[dict] = []
        self.updates: list[dict] = []

    async def touch_device(self, **values) -> None:
        self.devices.append(values)

    async def create_agent_run(self, **values) -> None:
        pass

    async def append_agent_event(self, **values) -> bool:
        self.events.append(values)
        return self.inserted

    async def update_agent_run(self, **values) -> None:
        self.updates.append(values)


class FakeWebSocket:
    def __init__(self, frames: list[dict], token: str = "device-token") -> None:
        self.request_headers = {"Authorization": f"Bearer {token}"}
        self.frames = deque(json.dumps(item) for item in frames)
        self.sent: list[dict] = []

    async def recv(self):
        if not self.frames:
            raise RuntimeError("connection closed")
        return self.frames.popleft()

    async def send(self, value: str) -> None:
        self.sent.append(json.loads(value))


class RelayWebSocketServerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        now = datetime.now(timezone.utc)
        self.claims = DeviceCredentialClaims(
            credential_id="cred-1",
            account_user_id="user-1",
            device_id="legion",
            scopes=frozenset({"relay.connect", "agent.receive"}),
            issued_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(days=30),
        )

    @staticmethod
    def hello(device_id: str = "legion") -> dict:
        return {
            "protocol_version": 1,
            "type": "hello",
            "device_id": device_id,
            "display_name": "Legion Y9000X",
            "capabilities": ["agent.chat"],
        }

    async def test_authenticated_hello_registers_device_then_cleans_up(self) -> None:
        registry = RelayRegistry()
        verifier = FakeVerifier(self.claims)
        server = RelayWebSocketServer(registry, verifier)
        websocket = FakeWebSocket([self.hello()])

        with self.assertRaises(RuntimeError):
            await server.handle(websocket)

        self.assertEqual(verifier.tokens, ["device-token"])
        self.assertEqual(websocket.sent[0]["type"], "hello_ack")
        self.assertFalse(registry.is_online("user-1", "legion"))

    async def test_event_is_persisted_and_acknowledged(self) -> None:
        store = FakeStore()
        server = RelayWebSocketServer(
            RelayRegistry(),
            FakeVerifier(self.claims),
            store,
        )
        websocket = FakeWebSocket(
            [
                self.hello(),
                {
                    "protocol_version": 1,
                    "type": "event",
                    "device_id": "legion",
                    "run_id": "run-1",
                    "seq": 0,
                    "event_type": "request_started",
                    "payload": {"request_id": "local-1"},
                },
            ]
        )

        with self.assertRaises(RuntimeError):
            await server.handle(websocket)

        self.assertEqual(len(store.devices), 1)
        self.assertEqual(store.events[0]["run_id"], "run-1")
        self.assertEqual(store.events[0]["seq"], 0)
        self.assertEqual(store.updates[0]["values"]["local_request_id"], "local-1")
        self.assertEqual(websocket.sent[-1]["type"], "event_ack")
        self.assertEqual(websocket.sent[-1]["seq"], 0)

    async def test_duplicate_persisted_event_is_still_acknowledged(self) -> None:
        store = FakeStore(inserted=False)
        server = RelayWebSocketServer(
            RelayRegistry(),
            FakeVerifier(self.claims),
            store,
        )
        websocket = FakeWebSocket(
            [
                self.hello(),
                {
                    "protocol_version": 1,
                    "type": "event",
                    "device_id": "legion",
                    "run_id": "run-1",
                    "seq": 4,
                    "event_type": "text_delta",
                    "payload": {"text": "again"},
                },
            ]
        )

        with self.assertRaises(RuntimeError):
            await server.handle(websocket)

        self.assertEqual(store.updates, [])
        self.assertEqual(websocket.sent[-1]["type"], "event_ack")
        self.assertEqual(websocket.sent[-1]["seq"], 4)

    async def test_credential_device_must_match_hello(self) -> None:
        server = RelayWebSocketServer(RelayRegistry(), FakeVerifier(self.claims))
        websocket = FakeWebSocket([self.hello("other-device")])
        with self.assertRaises(PermissionError):
            await server.handle(websocket)

    async def test_protocol_version_is_required(self) -> None:
        server = RelayWebSocketServer(RelayRegistry(), FakeVerifier(self.claims))
        frame = self.hello()
        frame.pop("protocol_version")
        websocket = FakeWebSocket([frame])
        with self.assertRaises(ValueError):
            await server.handle(websocket)

    async def test_missing_bearer_token_is_rejected_before_verification(self) -> None:
        verifier = FakeVerifier(self.claims)
        server = RelayWebSocketServer(RelayRegistry(), verifier)
        websocket = FakeWebSocket([], token="")
        with self.assertRaises(PermissionError):
            await server.handle(websocket)
        self.assertEqual(verifier.tokens, [])


if __name__ == "__main__":
    unittest.main()
