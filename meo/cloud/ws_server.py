from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from meo.cloud.enrollment import DeviceCredentialClaims
from meo.cloud.relay import RelayRegistry, RelaySession
from meo.cloud.store import CloudStore


PROTOCOL_VERSION = 1
_AGENT_RUN_STATUSES = {
    "queued",
    "dispatching",
    "running",
    "awaiting_approval",
    "cancel_requested",
    "completed",
    "cancelled",
    "failed",
}


class DeviceCredentialVerifier(Protocol):
    async def verify(self, bearer_token: str) -> DeviceCredentialClaims: ...


@dataclass
class RelayWebSocketServer:
    registry: RelayRegistry
    verifier: DeviceCredentialVerifier
    store: CloudStore | None = None

    async def authenticate(self, websocket: Any) -> DeviceCredentialClaims:
        """Authenticate before a real server upgrades the connection when possible."""
        token = self._bearer_token(websocket)
        claims = await self.verifier.verify(token)
        claims.validate()
        if not claims.allows("relay.connect"):
            raise PermissionError("device credential does not allow relay connection")
        return claims

    async def handle(
        self,
        websocket: Any,
        *,
        claims: DeviceCredentialClaims | None = None,
    ) -> None:
        if claims is None:
            claims = await self.authenticate(websocket)
        else:
            claims.validate()
            if not claims.allows("relay.connect"):
                raise PermissionError("device credential does not allow relay connection")

        first = await self._receive_json(websocket)
        self._require_protocol(first)
        if first.get("type") != "hello":
            raise ValueError("first relay frame must be hello")
        device_id = self._required_text(first, "device_id")
        display_name = self._required_text(first, "display_name")
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
        if self.store is not None:
            await self.store.touch_device(
                user_id=session.account_user_id,
                device_id=session.device_id,
                display_name=display_name,
                capabilities=session.capabilities,
            )
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
                await self._handle_device_message(
                    session,
                    display_name,
                    connection,
                    message,
                )
        finally:
            self.registry.unregister(device_id, connection)

    async def _handle_device_message(
        self,
        session: RelaySession,
        display_name: str,
        connection: "_WebSocketConnection",
        message: dict,
    ) -> None:
        message_type = message.get("type")
        if message_type == "pong":
            return
        if message_type not in {
            "heartbeat",
            "dispatch_ack",
            "cancel_ack",
            "decision_ack",
            "event",
        }:
            raise ValueError(f"unsupported device relay message: {message_type}")

        device_id = message.get("device_id", session.device_id)
        if device_id != session.device_id:
            raise PermissionError("relay frame device identity mismatch")

        if self.store is None:
            return

        if message_type == "heartbeat":
            await self.store.touch_device(
                user_id=session.account_user_id,
                device_id=session.device_id,
                display_name=display_name,
                capabilities=session.capabilities,
            )
            return

        if message_type == "dispatch_ack":
            run_id = self._required_text(message, "run_id")
            status = self._run_status(message.get("status"))
            # Only persisted events advance the cloud cursor. A dispatch ack
            # can carry -1 before any event is delivered, including on replay.
            values: dict[str, Any] = {"status": status}
            await self.store.update_agent_run(
                user_id=session.account_user_id,
                run_id=run_id,
                values=values,
            )
            return

        if message_type == "cancel_ack":
            await self.store.update_agent_run(
                user_id=session.account_user_id,
                run_id=self._required_text(message, "run_id"),
                values={"status": self._run_status(message.get("status"))},
            )
            return

        if message_type == "decision_ack":
            self._required_text(message, "run_id")
            self._required_text(message, "decision_id")
            return

        run_id = self._required_text(message, "run_id")
        seq = self._event_seq_or_default(message.get("seq"), None)
        event_type = self._required_text(message, "event_type")
        payload = message.get("payload", {})
        if not isinstance(payload, dict):
            raise ValueError("event payload must be an object")
        inserted = await self.store.append_agent_event(
            user_id=session.account_user_id,
            run_id=run_id,
            seq=seq,
            event_type=event_type,
            payload=payload,
        )

        if inserted:
            values: dict[str, Any] = {"last_event_seq": seq}
            if event_type == "request_started":
                request_id = payload.get("request_id")
                if isinstance(request_id, str) and request_id.strip():
                    values["local_request_id"] = request_id.strip()
                    values["status"] = "running"
            elif event_type == "done":
                status = payload.get("status")
                values["status"] = self._run_status(status)
            elif event_type == "error":
                values["status"] = "failed"
                code = payload.get("code")
                if isinstance(code, str) and code.strip():
                    values["error_code"] = code.strip()
            elif event_type == "tool_event":
                event = payload.get("event")
                if isinstance(event, dict) and event.get("type") == "tool.requested":
                    values["status"] = "awaiting_approval"
                elif isinstance(event, dict) and event.get("type") == "tool.completed":
                    values["status"] = "running"

            await self.store.update_agent_run(
                user_id=session.account_user_id,
                run_id=run_id,
                values=values,
            )

        # A duplicate event is also acknowledged. Its unique (run_id, seq) row
        # proves it was persisted by this or an earlier connection attempt.
        await connection.send_json(
            {
                "protocol_version": PROTOCOL_VERSION,
                "type": "event_ack",
                "run_id": run_id,
                "seq": seq,
            }
        )

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

    @staticmethod
    def _run_status(value: Any) -> str:
        if not isinstance(value, str) or value not in _AGENT_RUN_STATUSES:
            raise ValueError("invalid AgentRun status")
        return value

    @staticmethod
    def _event_seq_or_default(value: Any, default: int | None) -> int:
        if value is None and default is not None:
            return default
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("event sequence must be a non-negative integer")
        return value


class _WebSocketConnection:
    def __init__(self, websocket: Any) -> None:
        self.websocket = websocket

    async def send_json(self, payload: dict) -> None:
        await self.websocket.send(json.dumps(payload, separators=(",", ":")))
