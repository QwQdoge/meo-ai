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
    async def test_send_json_uses_compact_text_frame(self) -> None:
        websocket = FakeWebSocket()
        connection = WebSocketRelayConnection(websocket)

        await connection.send_json({"type": "ping", "value": 1})

        self.assertEqual(websocket.sent, ['{"type":"ping","value":1}'])

    async def test_receive_json_accepts_text_or_utf8_bytes(self) -> None:
        websocket = FakeWebSocket()
        websocket.received = ['{"type":"pong"}', b'{"type":"heartbeat"}']
        connection = WebSocketRelayConnection(websocket)

        self.assertEqual(await connection.receive_json(), {"type": "pong"})
        self.assertEqual(await connection.receive_json(), {"type": "heartbeat"})

    async def test_receive_json_rejects_non_object(self) -> None:
        websocket = FakeWebSocket()
        websocket.received = ['[1,2,3]']
        connection = WebSocketRelayConnection(websocket)

        with self.assertRaises(ValueError):
            await connection.receive_json()

    async def test_close_delegates_to_websocket(self) -> None:
        websocket = FakeWebSocket()
        connection = WebSocketRelayConnection(websocket)

        await connection.close()

        self.assertTrue(websocket.closed)


if __name__ == "__main__":
    unittest.main()
