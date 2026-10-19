from __future__ import annotations

from datetime import datetime
from typing import Protocol


class CloudStore(Protocol):
    async def list_conversations(
        self, *, user_id: str, limit: int = 50, before: tuple[str, str] | None = None,
    ) -> tuple[dict, ...]: ...

    async def create_conversation(self, *, user_id: str, title: str) -> dict: ...

    async def get_conversation(self, *, user_id: str, conversation_id: str) -> dict | None: ...

    async def list_conversation_messages(
        self, *, user_id: str, conversation_id: str, limit: int = 500,
    ) -> tuple[dict, ...]: ...

    async def append_conversation_message(
        self, *, user_id: str, conversation_id: str, role: str, content: str,
    ) -> dict: ...

    async def list_agent_runs(
        self, *, user_id: str, limit: int = 30,
    ) -> tuple[dict, ...]: ...

    async def list_agent_events(
        self, *, user_id: str, run_id: str, after: int, limit: int = 100,
    ) -> tuple[dict, ...]: ...

    async def touch_device(
        self,
        *,
        user_id: str,
        device_id: str,
        display_name: str,
        capabilities: tuple[str, ...],
    ) -> None: ...

    async def create_agent_run(
        self,
        *,
        run_id: str,
        user_id: str,
        conversation_id: str | None,
        device_id: str,
        status: str,
        project_id: str | None = None,
        workspace_ref: str | None = None,
        permission_mode: str = "smart",
        requested_capabilities: tuple[str, ...] = ("agent.chat",),
    ) -> None: ...

    async def append_agent_event(
        self,
        *,
        user_id: str,
        run_id: str,
        seq: int,
        event_type: str,
        payload: dict,
    ) -> bool: ...

    async def update_agent_run(
        self,
        *,
        user_id: str,
        run_id: str,
        values: dict,
    ) -> None: ...

    async def list_project_locations(
        self,
        *,
        user_id: str,
        project_id: str,
    ) -> tuple[dict, ...]: ...

    async def get_agent_run(
        self,
        *,
        user_id: str,
        run_id: str,
    ) -> dict | None: ...

    async def get_device_credential_by_hash(
        self,
        *,
        token_hash: str,
    ) -> dict | None: ...

    async def create_device_enrollment(
        self,
        *,
        enrollment_id: str,
        secret_hash: str,
        user_code: str,
        device_id: str,
        display_name: str,
        capabilities: tuple[str, ...],
        requested_scopes: tuple[str, ...],
        expires_at: datetime,
    ) -> None: ...

    async def get_device_enrollment_by_code(self, *, user_code: str) -> dict | None: ...

    async def get_device_enrollment_by_secret_hash(
        self,
        *,
        secret_hash: str,
    ) -> dict | None: ...

    async def approve_device_enrollment(
        self,
        *,
        enrollment_id: str,
        user_id: str,
    ) -> dict | None: ...

    async def consume_device_enrollment(
        self,
        *,
        secret_hash: str,
        token_hash: str,
        credential_expires_at: datetime,
    ) -> dict | None: ...

    async def has_recent_reauth(
        self,
        *,
        user_id: str,
        session_id: str,
        purpose: str,
    ) -> bool: ...




class CloudStoreConflict(RuntimeError):
    """A conflicting cloud record; shared by pairing and persistence adapters."""
