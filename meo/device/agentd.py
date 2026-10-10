from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import asyncio
import json
import random
from typing import Awaitable, Callable, Protocol

from meo.device.events import RelayEventQueue
from meo.device.protocol import AgentRunBinding, AgentRunStatus, DeviceRegistration


class AgentdState(str, Enum):
    STOPPED = "stopped"
    CONNECTING = "connecting"
    ONLINE = "online"
    BACKOFF = "backoff"


@dataclass(frozen=True)
class AgentdConfig:
    device: DeviceRegistration
    relay_url: str
    heartbeat_seconds: float = 20.0
    reconnect_min_seconds: float = 1.0
    reconnect_max_seconds: float = 30.0

    def validate(self) -> None:
        self.device.validate()
        if not self.relay_url.startswith("wss://"):
            raise ValueError("relay_url must use wss://")
        if self.heartbeat_seconds <= 0:
            raise ValueError("heartbeat_seconds must be positive")
        if self.reconnect_min_seconds <= 0:
            raise ValueError("reconnect_min_seconds must be positive")
        if self.reconnect_max_seconds < self.reconnect_min_seconds:
            raise ValueError("reconnect_max_seconds must be >= reconnect_min_seconds")


class DeviceSecretProvider(Protocol):
    async def get_device_token(self) -> str: ...


class RelayConnection(Protocol):
    async def send_json(self, payload: dict) -> None: ...

    async def receive_json(self) -> dict: ...

    async def close(self) -> None: ...


class RelayConnector(Protocol):
    async def __call__(self, config: AgentdConfig, device_token: str) -> RelayConnection: ...


class AgentRunExecutor(Protocol):
    async def dispatch(self, run: AgentRunBinding, payload: dict) -> None: ...

    async def cancel(self, run: AgentRunBinding) -> None: ...

    async def decide(self, run: AgentRunBinding, decision_id: str, option_index: int) -> None: ...


class MeoAgentd:
    """Transport coordinator for one enrolled Meo device.

    Persisted configuration is intentionally non-secret. A narrow device token is
    loaded at connection time from an injected secure-storage provider. This layer
    does not expose arbitrary remote shell execution; it accepts typed relay
    messages and delegates local work to the existing AgentService boundary.
    """

    def __init__(
        self,
        config: AgentdConfig,
        secrets: DeviceSecretProvider,
        connector: RelayConnector,
        executor: AgentRunExecutor,
        *,
        events: RelayEventQueue | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        config.validate()
        self.config = config
        self.secrets = secrets
        self.connector = connector
        self.executor = executor
        self.events = events
        self.sleep = sleep
        self.jitter = jitter
        self.state = AgentdState.STOPPED
        self.runs: dict[str, AgentRunBinding] = {}
        self._stop_requested = False

    async def run_forever(self) -> None:
        delay = self.config.reconnect_min_seconds
        self._stop_requested = False
        while not self._stop_requested:
            self.state = AgentdState.CONNECTING
            connection: RelayConnection | None = None
            try:
                device_token = (await self.secrets.get_device_token()).strip()
                if not device_token:
                    raise RuntimeError("device credential is unavailable")
                connection = await self.connector(self.config, device_token)
                delay = self.config.reconnect_min_seconds
                self.state = AgentdState.ONLINE
                await self._serve(connection)
            except asyncio.CancelledError:
                raise
            except Exception:
                if self._stop_requested:
                    break
                self.state = AgentdState.BACKOFF
                wait = min(delay, self.config.reconnect_max_seconds)
                await self.sleep(wait + self.jitter() * min(wait, 1.0))
                delay = min(delay * 2.0, self.config.reconnect_max_seconds)
            finally:
                if connection is not None:
                    try:
                        await connection.close()
                    except Exception:
                        pass
        self.state = AgentdState.STOPPED

    async def stop(self) -> None:
        self._stop_requested = True

    async def _serve(self, connection: RelayConnection) -> None:
        await connection.send_json(
            {
                "type": "hello",
                "device_id": self.config.device.device_id,
                "display_name": self.config.device.display_name,
                "capabilities": list(self.config.device.capabilities),
            }
        )

        heartbeat_task = asyncio.create_task(self._heartbeat_loop(connection))
        event_task: asyncio.Task | None = None
        if self.events is not None:
            self.events.requeue_all()
            event_task = asyncio.create_task(self.events.send_loop(connection))
        try:
            while not self._stop_requested:
                message = await connection.receive_json()
                await self.handle_message(connection, message)
        finally:
            tasks = [heartbeat_task]
            if event_task is not None:
                tasks.append(event_task)
            for task in tasks:
                task.cancel()
            for task in tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _heartbeat_loop(self, connection: RelayConnection) -> None:
        while True:
            await self.sleep(self.config.heartbeat_seconds)
            await connection.send_json(
                {
                    "type": "heartbeat",
                    "device_id": self.config.device.device_id,
                    "active_runs": [
                        run_id for run_id, run in self.runs.items() if not run.terminal
                    ],
                }
            )

    async def handle_message(self, connection: RelayConnection, message: dict) -> None:
        if not isinstance(message, dict):
            raise ValueError("relay message must be an object")
        message_type = message.get("type")
        if message_type == "hello_ack":
            device_id = self._required_text(message, "device_id")
            if device_id != self.config.device.device_id:
                raise ValueError("relay acknowledged a different device")
            return
        if message_type == "event_ack":
            if self.events is None:
                return
            run_id = self._required_text(message, "run_id")
            seq = message.get("seq")
            if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
                raise ValueError("event ack seq must be a non-negative integer")
            self.events.acknowledge(run_id, seq)
            return
        if message_type == "dispatch":
            await self._handle_dispatch(connection, message)
            return
        if message_type == "cancel":
            await self._handle_cancel(connection, message)
            return
        if message_type == "decision":
            await self._handle_decision(connection, message)
            return
        if message_type == "ping":
            await connection.send_json({"type": "pong"})
            return
        raise ValueError(f"unsupported relay message type: {message_type}")

    async def _handle_dispatch(self, connection: RelayConnection, message: dict) -> None:
        run_id = self._required_text(message, "run_id")
        conversation_id = self._required_text(message, "conversation_id")
        device_id = self._required_text(message, "device_id")
        if device_id != self.config.device.device_id:
            raise ValueError("dispatch target does not match this device")

        existing = self.runs.get(run_id)
        if existing is not None:
            if existing.conversation_id != conversation_id or existing.device_id != device_id:
                raise ValueError("existing AgentRun identity does not match dispatch")
            await connection.send_json(
                {
                    "type": "dispatch_ack",
                    "run_id": run_id,
                    "status": existing.status.value,
                    "reused": True,
                    "last_event_seq": existing.last_event_seq,
                }
            )
            return

        run = AgentRunBinding(run_id, conversation_id, device_id)
        run.transition(AgentRunStatus.DISPATCHING)
        self.runs[run_id] = run
        try:
            await self.executor.dispatch(run, message)
            if run.status is AgentRunStatus.DISPATCHING:
                run.transition(AgentRunStatus.RUNNING)
        except Exception:
            if not run.terminal:
                run.transition(AgentRunStatus.FAILED)
            raise

        await connection.send_json(
            {
                "type": "dispatch_ack",
                "run_id": run_id,
                "status": run.status.value,
                "reused": False,
                "last_event_seq": run.last_event_seq,
            }
        )

    async def _handle_cancel(self, connection: RelayConnection, message: dict) -> None:
        run = self._require_run(message)
        if run.terminal:
            await connection.send_json(
                {"type": "cancel_ack", "run_id": run.run_id, "status": run.status.value}
            )
            return
        if run.status is not AgentRunStatus.CANCEL_REQUESTED:
            run.transition(AgentRunStatus.CANCEL_REQUESTED)
        await self.executor.cancel(run)
        await connection.send_json(
            {"type": "cancel_ack", "run_id": run.run_id, "status": run.status.value}
        )

    async def _handle_decision(self, connection: RelayConnection, message: dict) -> None:
        run = self._require_run(message)
        decision_id = self._required_text(message, "decision_id")
        option_index = message.get("option_index")
        if not isinstance(option_index, int) or isinstance(option_index, bool) or option_index < 0:
            raise ValueError("option_index must be a non-negative integer")
        if run.status is not AgentRunStatus.AWAITING_APPROVAL:
            raise ValueError("AgentRun is not awaiting approval")
        # The backend may synchronously finish or request another approval while
        # consuming this choice. Preserve the state reported by those callbacks.
        run.transition(AgentRunStatus.RUNNING)
        try:
            await self.executor.decide(run, decision_id, option_index)
        except Exception:
            if run.status is AgentRunStatus.RUNNING:
                run.transition(AgentRunStatus.AWAITING_APPROVAL)
            raise
        await connection.send_json(
            {"type": "decision_ack", "run_id": run.run_id, "decision_id": decision_id}
        )

    def _require_run(self, message: dict) -> AgentRunBinding:
        run_id = self._required_text(message, "run_id")
        try:
            return self.runs[run_id]
        except KeyError as exc:
            raise ValueError("unknown AgentRun") from exc

    @staticmethod
    def _required_text(message: dict, key: str) -> str:
        value = message.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} is required")
        return value.strip()


def config_from_json(value: str) -> AgentdConfig:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("agentd config must be a JSON object")
    if "device_token" in payload or "token" in payload:
        raise ValueError("device credentials must not be stored in agentd config")
    capabilities = payload.get("capabilities", [])
    if not isinstance(capabilities, list):
        raise ValueError("capabilities must be a list")
    device = DeviceRegistration.create(
        payload.get("device_id", ""),
        payload.get("display_name", ""),
        capabilities,
    )
    config = AgentdConfig(
        device=device,
        relay_url=str(payload.get("relay_url", "")),
        heartbeat_seconds=float(payload.get("heartbeat_seconds", 20.0)),
        reconnect_min_seconds=float(payload.get("reconnect_min_seconds", 1.0)),
        reconnect_max_seconds=float(payload.get("reconnect_max_seconds", 30.0)),
    )
    config.validate()
    return config
