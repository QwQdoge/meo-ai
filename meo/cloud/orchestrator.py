from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from meo.cloud.policy import PermissionMode
from meo.cloud.relay import RelayRegistry
from meo.cloud.store import CloudStore


@dataclass(frozen=True)
class AgentRunRequest:
    conversation_id: str
    text: str
    project_id: str | None = None
    preferred_device_id: str | None = None
    permission_mode: PermissionMode = PermissionMode.SMART

    def validate(self) -> None:
        if not self.conversation_id.strip():
            raise ValueError("conversation_id is required")
        if not self.text.strip():
            raise ValueError("text is required")
        if len(self.text) > 100_000:
            raise ValueError("text is too large")
        if self.project_id is not None and not self.project_id.strip():
            raise ValueError("project_id must be non-empty when provided")
        if self.preferred_device_id is not None and not self.preferred_device_id.strip():
            raise ValueError("preferred_device_id must be non-empty when provided")


@dataclass(frozen=True)
class ResolvedDevice:
    device_id: str
    workspace_ref: str | None = None

    def validate(self) -> None:
        if not self.device_id.strip():
            raise ValueError("resolved device_id is required")


class DeviceResolver(Protocol):
    async def resolve(
        self,
        *,
        user_id: str,
        project_id: str | None,
        preferred_device_id: str | None,
        required_capability: str,
    ) -> ResolvedDevice: ...


@dataclass(frozen=True)
class AgentRunCreated:
    run_id: str
    device_id: str
    status: str
    permission_mode: PermissionMode


class AgentRunOrchestrator:
    """Create and dispatch one remote AgentRun with minimal client input.

    The browser supplies conversational intent, not local shell commands or raw
    filesystem paths. Device/workspace routing is server-owned via DeviceResolver.
    """

    def __init__(
        self,
        *,
        store: CloudStore,
        relay: RelayRegistry,
        resolver: DeviceResolver,
    ) -> None:
        self.store = store
        self.relay = relay
        self.resolver = resolver

    async def create_and_dispatch(
        self,
        *,
        user_id: str,
        request: AgentRunRequest,
    ) -> AgentRunCreated:
        user_id = user_id.strip()
        if not user_id:
            raise ValueError("authenticated user_id is required")
        request.validate()

        resolved = await self.resolver.resolve(
            user_id=user_id,
            project_id=request.project_id,
            preferred_device_id=request.preferred_device_id,
            required_capability="agent.chat",
        )
        resolved.validate()

        run_id = str(uuid4())
        await self.store.create_agent_run(
            run_id=run_id,
            user_id=user_id,
            conversation_id=request.conversation_id.strip(),
            device_id=resolved.device_id,
            status="queued",
        )

        try:
            await self.relay.dispatch_agent_run(
                account_user_id=user_id,
                device_id=resolved.device_id,
                run_id=run_id,
                conversation_id=request.conversation_id.strip(),
                text=request.text.strip(),
                required_capability="agent.chat",
            )
        except ConnectionError:
            await self.store.update_agent_run(
                user_id=user_id,
                run_id=run_id,
                values={"status": "failed", "error_code": "device_offline"},
            )
            raise
        except PermissionError:
            await self.store.update_agent_run(
                user_id=user_id,
                run_id=run_id,
                values={"status": "failed", "error_code": "device_not_allowed"},
            )
            raise
        except Exception:
            await self.store.update_agent_run(
                user_id=user_id,
                run_id=run_id,
                values={"status": "failed", "error_code": "dispatch_failed"},
            )
            raise

        await self.store.update_agent_run(
            user_id=user_id,
            run_id=run_id,
            values={"status": "dispatching"},
        )
        return AgentRunCreated(
            run_id=run_id,
            device_id=resolved.device_id,
            status="dispatching",
            permission_mode=request.permission_mode,
        )
