from __future__ import annotations

import unittest

from meo.device.websocket_transport import WebSocketRelayConnection


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.received: list[object] = []
        self.closed = False

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    async def recv(self):
        return self.received.pop(0)

    async def close(self) -> None:
        self.closed = True


class WebSocketRelayConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_json_injects_protocol_version(self) -> None:
        websocket = FakeWebSocket()
        connection = WebSocketRelayConnection(websocket)

        await connection.send_json({"type": "ping", "value": 1})

        self.assertEqual(
            websocket.sent,
            ['{"type":"ping","value":1,"protocol_version":1}'],
        )

    async def test_receive_json_accepts_versioned_text_or_utf8_bytes(self) -> None:
        websocket = FakeWebSocket()
        websocket.received = [
            '{"protocol_version":1,"type":"pong"}',
            b'{"protocol_version":1,"type":"heartbeat"}',
        ]
        connection = WebSocketRelayConnection(websocket)

        self.assertEqual(
            await connection.receive_json(),
            {"protocol_version": 1, "type": "pong"},
        )
        self.assertEqual(
            await connection.receive_json(),
            {"protocol_version": 1, "type": "heartbeat"},
        )

    async def test_receive_json_rejects_non_object_or_wrong_version(self) -> None:
        websocket = FakeWebSocket()
        websocket.received = ['[1,2,3]']
        connection = WebSocketRelayConnection(websocket)
        with self.assertRaises(ValueError):
            await connection.receive_json()

        websocket.received = ['{"protocol_version":2,"type":"pong"}']
        with self.assertRaises(ValueError):
            await connection.receive_json()

    async def test_close_delegates_to_websocket(self) -> None:
        websocket = FakeWebSocket()
        connection = WebSocketRelayConnection(websocket)

        await connection.close()

        self.assertTrue(websocket.closed)


if __name__ == "__main__":
    unittest.main()
