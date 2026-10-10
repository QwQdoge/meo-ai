from __future__ import annotations

import json
from typing import Any

from meo.device.agentd import AgentdConfig


PROTOCOL_VERSION = 1


class WebSocketRelayConnection:
    def __init__(self, websocket: Any) -> None:
        self.websocket = websocket

    async def send_json(self, payload: dict) -> None:
        envelope = dict(payload)
        envelope.setdefault("protocol_version", PROTOCOL_VERSION)
        await self.websocket.send(json.dumps(envelope, separators=(",", ":")))

    async def receive_json(self) -> dict:
        raw = await self.websocket.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            raise ValueError("relay frame must be text JSON")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("relay message must be a JSON object")
        version = value.get("protocol_version")
        if version != PROTOCOL_VERSION:
            raise ValueError("unsupported relay protocol version")
        return value

    async def close(self) -> None:
        await self.websocket.close()


async def connect_websocket_relay(
    config: AgentdConfig,
    device_token: str,
) -> WebSocketRelayConnection:
    """Connect to the Meo relay using a narrow device bearer credential.

    `websockets` is an optional runtime dependency for remote-device support.
    Importing the rest of Meo AgentService doesn't require it.
    """

    try:
        from websockets.asyncio.client import connect
    except ImportError as exc:
        raise RuntimeError(
            "Remote device support requires the 'websockets' Python package"
        ) from exc

    token = device_token.strip()
    if not token:
        raise ValueError("device credential is required")

    websocket = await connect(
        config.relay_url,
        additional_headers={"Authorization": f"Bearer {token}"},
        subprotocols=["meo-agentd.v1"],
        open_timeout=15,
        ping_interval=20,
        ping_timeout=20,
        max_size=1_048_576,
        max_queue=16,
    )
    return WebSocketRelayConnection(websocket)
