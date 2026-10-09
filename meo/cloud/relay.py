from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RelaySession:
    account_user_id: str
    device_id: str
    capabilities: tuple[str, ...]

    def validate(self) -> None:
        if not self.account_user_id or not self.device_id:
            raise ValueError("relay session identity is incomplete")
        if any(not item for item in self.capabilities):
            raise ValueError("relay capability IDs must be non-empty")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("relay capability IDs must be unique")


class DeviceConnection(Protocol):
    async def send_json(self, payload: dict) -> None: ...


class RelayRegistry:
    """In-memory online-device registry used by the first relay server.

    Production persistence belongs to the cloud database, but live WebSocket
    ownership is process-local. A later multi-replica relay can replace this
    registry behind the same API with Redis/pubsub without changing agentd.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, RelaySession] = {}
        self._connections: dict[str, DeviceConnection] = {}

    def register(
        self,
        session: RelaySession,
        connection: DeviceConnection,
    ) -> None:
        session.validate()
        existing = self._sessions.get(session.device_id)
        if existing is not None and existing.account_user_id != session.account_user_id:
            raise PermissionError("device is already owned by another account")
        self._sessions[session.device_id] = session
        self._connections[session.device_id] = connection

    def unregister(self, device_id: str, connection: DeviceConnection) -> None:
        current = self._connections.get(device_id)
        if current is not connection:
            return
        self._connections.pop(device_id, None)
        self._sessions.pop(device_id, None)

    def get_session(self, device_id: str) -> RelaySession | None:
        return self._sessions.get(device_id)

    def get_connection(self, device_id: str) -> DeviceConnection | None:
        return self._connections.get(device_id)

    def is_online(self, account_user_id: str, device_id: str) -> bool:
        session = self._sessions.get(device_id)
        return bool(session and session.account_user_id == account_user_id)

    async def dispatch_agent_run(
        self,
        *,
        account_user_id: str,
        device_id: str,
        run_id: str,
        conversation_id: str,
        text: str,
        required_capability: str = "agent.chat",
    ) -> None:
        if not run_id or not conversation_id or not text.strip():
            raise ValueError("AgentRun dispatch is incomplete")
        session = self._sessions.get(device_id)
        connection = self._connections.get(device_id)
        if session is None or connection is None:
            raise ConnectionError("device is offline")
        if session.account_user_id != account_user_id:
            raise PermissionError("device does not belong to this account")
        if required_capability not in session.capabilities:
            raise PermissionError("device does not advertise required capability")
        await connection.send_json(
            {
                "protocol_version": 1,
                "type": "dispatch",
                "run_id": run_id,
                "conversation_id": conversation_id,
                "device_id": device_id,
                "text": text,
            }
        )

    async def cancel_agent_run(
        self,
        *,
        account_user_id: str,
        device_id: str,
        run_id: str,
    ) -> None:
        connection = self._owned_connection(account_user_id, device_id)
        await connection.send_json(
            {
                "protocol_version": 1,
                "type": "cancel",
                "run_id": run_id,
            }
        )

    async def submit_decision(
        self,
        *,
        account_user_id: str,
        device_id: str,
        run_id: str,
        decision_id: str,
        option_index: int,
    ) -> None:
        if not decision_id:
            raise ValueError("decision_id is required")
        if not isinstance(option_index, int) or isinstance(option_index, bool) or option_index < 0:
            raise ValueError("option_index must be a non-negative integer")
        connection = self._owned_connection(account_user_id, device_id)
        await connection.send_json(
            {
                "protocol_version": 1,
                "type": "decision",
                "run_id": run_id,
                "decision_id": decision_id,
                "option_index": option_index,
            }
        )

    def _owned_connection(self, account_user_id: str, device_id: str) -> DeviceConnection:
        session = self._sessions.get(device_id)
        connection = self._connections.get(device_id)
        if session is None or connection is None:
            raise ConnectionError("device is offline")
        if session.account_user_id != account_user_id:
            raise PermissionError("device does not belong to this account")
        return connection
