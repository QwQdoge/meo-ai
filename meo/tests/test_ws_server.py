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

    async def test_authenticated_hello_registers_device_then_cleans_up(self) -> None:
        registry = RelayRegistry()
        verifier = FakeVerifier(self.claims)
        server = RelayWebSocketServer(registry, verifier)
        websocket = FakeWebSocket(
            [
                {
                    "protocol_version": 1,
                    "type": "hello",
                    "device_id": "legion",
                    "display_name": "Legion Y9000X",
                    "capabilities": ["agent.chat"],
                }
            ]
        )

        with self.assertRaises(RuntimeError):
            await server.handle(websocket)

        self.assertEqual(verifier.tokens, ["device-token"])
        self.assertEqual(websocket.sent[0]["type"], "hello_ack")
        self.assertFalse(registry.is_online("user-1", "legion"))

    async def test_credential_device_must_match_hello(self) -> None:
        server = RelayWebSocketServer(RelayRegistry(), FakeVerifier(self.claims))
        websocket = FakeWebSocket(
            [
                {
                    "protocol_version": 1,
                    "type": "hello",
                    "device_id": "other-device",
                    "capabilities": ["agent.chat"],
                }
            ]
        )
        with self.assertRaises(PermissionError):
            await server.handle(websocket)

    async def test_protocol_version_is_required(self) -> None:
        server = RelayWebSocketServer(RelayRegistry(), FakeVerifier(self.claims))
        websocket = FakeWebSocket(
            [
                {
                    "type": "hello",
                    "device_id": "legion",
                    "capabilities": ["agent.chat"],
                }
            ]
        )
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
