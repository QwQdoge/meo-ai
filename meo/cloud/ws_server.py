from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from meo.cloud.enrollment import DeviceCredentialClaims
from meo.cloud.relay import RelayRegistry, RelaySession


PROTOCOL_VERSION = 1


class DeviceCredentialVerifier(Protocol):
    async def verify(self, bearer_token: str) -> DeviceCredentialClaims: ...


@dataclass
class RelayWebSocketServer:
    registry: RelayRegistry
    verifier: DeviceCredentialVerifier

    async def handle(self, websocket: Any) -> None:
        token = self._bearer_token(websocket)
        claims = await self.verifier.verify(token)
        claims.validate()
        if not claims.allows("relay.connect"):
            raise PermissionError("device credential does not allow relay connection")

        first = await self._receive_json(websocket)
        self._require_protocol(first)
        if first.get("type") != "hello":
            raise ValueError("first relay frame must be hello")
        device_id = self._required_text(first, "device_id")
        if device_id != claims.device_id:
            raise PermissionError("hello device identity does not match credential")
        capabilities = first.get("capabilities")
        if not isinstance(capabilities, list) or any(
            not isinstance(item, str) or not item.strip() for item in capabilities
        ):
            raise ValueError("hello capabilities are invalid")
        normalized = tuple(item.strip() for item in capabilities)
        connection = _WebSocketConnection(websocket)
        session = RelaySession(
            account_user_id=claims.account_user_id,
            device_id=device_id,
            capabilities=normalized,
        )
        self.registry.register(session, connection)
        try:
            await connection.send_json(
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "type": "hello_ack",
                    "device_id": device_id,
                }
            )
            while True:
                message = await self._receive_json(websocket)
                self._require_protocol(message)
                await self._handle_device_message(session, message)
        finally:
            self.registry.unregister(device_id, connection)

    async def _handle_device_message(self, session: RelaySession, message: dict) -> None:
        message_type = message.get("type")
        if message_type in {
            "heartbeat",
            "dispatch_ack",
            "cancel_ack",
            "decision_ack",
            "event",
        }:
            device_id = message.get("device_id", session.device_id)
            if device_id != session.device_id:
                raise PermissionError("relay frame device identity mismatch")
            return
        if message_type == "pong":
            return
        raise ValueError(f"unsupported device relay message: {message_type}")

    @staticmethod
    def _bearer_token(websocket: Any) -> str:
        headers = getattr(websocket, "request_headers", None)
        if headers is None:
            request = getattr(websocket, "request", None)
            headers = getattr(request, "headers", None)
        authorization = headers.get("Authorization") if headers is not None else None
        if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
            raise PermissionError("device bearer credential is required")
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise PermissionError("device bearer credential is required")
        return token

    @staticmethod
    async def _receive_json(websocket: Any) -> dict:
        raw = await websocket.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            raise ValueError("relay frame must be text JSON")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("relay message must be a JSON object")
        return value

    @staticmethod
    def _require_protocol(payload: dict) -> None:
        version = payload.get("protocol_version")
        if version != PROTOCOL_VERSION:
            raise ValueError("unsupported relay protocol version")

    @staticmethod
    def _required_text(payload: dict, key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} is required")
        return value.strip()


class _WebSocketConnection:
    def __init__(self, websocket: Any) -> None:
        self.websocket = websocket

    async def send_json(self, payload: dict) -> None:
        await self.websocket.send(json.dumps(payload, separators=(",", ":")))
