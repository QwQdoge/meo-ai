from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class CloudStore(Protocol):
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


@dataclass(frozen=True)
class SupabaseRestConfig:
    project_url: str
    service_role_key: str

    def validate(self) -> None:
        if not self.project_url.startswith("https://"):
            raise ValueError("Supabase project URL must use https://")
        if not self.service_role_key.strip():
            raise ValueError("Supabase service role key is required")


class SupabaseRestStore:
    """Server-only persistence adapter for Meo AI cloud state.

    The service-role key must never be shipped to browser/native clients. All
    service-role reads include explicit owner filters where ownership is known;
    opaque credential lookups use only a one-way token hash.
    """

    def __init__(
        self,
        config: SupabaseRestConfig,
        *,
        request_json: Callable[..., Any] | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self._request_json_override = request_json

    async def touch_device(
        self,
        *,
        user_id: str,
        device_id: str,
        display_name: str,
        capabilities: tuple[str, ...],
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._request(
            "POST",
            "/rest/v1/ai_devices?on_conflict=user_id,device_id",
            {
                "user_id": user_id,
                "device_id": device_id,
                "display_name": display_name,
                "capabilities": list(capabilities),
                "last_seen_at": now,
                "updated_at": now,
            },
            prefer="resolution=merge-duplicates,return=minimal",
        )

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
    ) -> None:
        if permission_mode not in {"ask", "smart", "full_access"}:
            raise ValueError("invalid permission_mode")
        if not requested_capabilities or any(not item.strip() for item in requested_capabilities):
            raise ValueError("requested_capabilities must be non-empty")
        body: dict[str, Any] = {
            "id": run_id,
            "user_id": user_id,
            "device_id": device_id,
            "status": status,
            "permission_mode": permission_mode,
            "requested_capabilities": list(requested_capabilities),
        }
        if conversation_id is not None:
            body["conversation_id"] = conversation_id
        if project_id is not None:
            body["project_id"] = project_id
        if workspace_ref is not None:
            body["workspace_ref"] = workspace_ref
        await self._request(
            "POST",
            "/rest/v1/ai_agent_runs?on_conflict=id",
            body,
            prefer="resolution=ignore-duplicates,return=minimal",
        )

    async def append_agent_event(
        self,
        *,
        user_id: str,
        run_id: str,
        seq: int,
        event_type: str,
        payload: dict,
    ) -> bool:
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
            raise ValueError("event seq must be a non-negative integer")
        if not event_type.strip():
            raise ValueError("event_type is required")
        result = await self._request(
            "POST",
            "/rest/v1/ai_agent_events?on_conflict=run_id,seq",
            {
                "user_id": user_id,
                "run_id": run_id,
                "seq": seq,
                "event_type": event_type,
                "payload": payload,
            },
            prefer="resolution=ignore-duplicates,return=representation",
        )
        if isinstance(result, list):
            return bool(result)
        return result is not None

    async def update_agent_run(
        self,
        *,
        user_id: str,
        run_id: str,
        values: dict,
    ) -> None:
        allowed = {
            "status",
            "local_request_id",
            "last_event_seq",
            "error_code",
            "started_at",
            "finished_at",
            "updated_at",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"unsupported AgentRun fields: {sorted(unknown)}")
        body = dict(values)
        body.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
        query = urlencode({"id": f"eq.{run_id}", "user_id": f"eq.{user_id}"})
        await self._request(
            "PATCH",
            f"/rest/v1/ai_agent_runs?{query}",
            body,
            prefer="return=minimal",
        )

    async def list_project_locations(
        self,
        *,
        user_id: str,
        project_id: str,
    ) -> tuple[dict, ...]:
        query = urlencode(
            {
                "select": "device_id,workspace_ref",
                "user_id": f"eq.{user_id}",
                "project_id": f"eq.{project_id}",
                "order": "updated_at.desc",
            }
        )
        result = await self._request(
            "GET",
            f"/rest/v1/ai_project_locations?{query}",
            None,
        )
        if not isinstance(result, list):
            raise RuntimeError("Supabase project location response is invalid")
        rows: list[dict] = []
        for row in result:
            if not isinstance(row, dict):
                continue
            device_id = row.get("device_id")
            workspace_ref = row.get("workspace_ref")
            if isinstance(device_id, str) and device_id.strip() and isinstance(workspace_ref, str) and workspace_ref.strip():
                rows.append(
                    {
                        "device_id": device_id.strip(),
                        "workspace_ref": workspace_ref.strip(),
                    }
                )
        return tuple(rows)

    async def get_agent_run(
        self,
        *,
        user_id: str,
        run_id: str,
    ) -> dict | None:
        query = urlencode(
            {
                "select": "id,device_id,status,conversation_id,permission_mode,last_event_seq",
                "id": f"eq.{run_id}",
                "user_id": f"eq.{user_id}",
                "limit": "1",
            }
        )
        result = await self._request(
            "GET",
            f"/rest/v1/ai_agent_runs?{query}",
            None,
        )
        if not isinstance(result, list):
            raise RuntimeError("Supabase AgentRun response is invalid")
        if not result:
            return None
        row = result[0]
        return row if isinstance(row, dict) else None

    async def get_device_credential_by_hash(
        self,
        *,
        token_hash: str,
    ) -> dict | None:
        token_hash = token_hash.strip().lower()
        if len(token_hash) != 64 or any(ch not in "0123456789abcdef" for ch in token_hash):
            raise ValueError("token_hash must be a SHA-256 hex digest")
        query = urlencode(
            {
                "select": "id,user_id,device_id,scopes,issued_at,expires_at,revoked_at",
                "token_hash": f"eq.{token_hash}",
                "limit": "1",
            }
        )
        result = await self._request(
            "GET",
            f"/rest/v1/ai_device_credentials?{query}",
            None,
        )
        if not isinstance(result, list):
            raise RuntimeError("Supabase device credential response is invalid")
        if not result:
            return None
        row = result[0]
        return row if isinstance(row, dict) else None

    async def _request(
        self,
        method: str,
        path: str,
        body: dict | None,
        *,
        prefer: str | None = None,
    ) -> Any:
        if self._request_json_override is not None:
            result = self._request_json_override(method, path, body, prefer)
            if asyncio.iscoroutine(result):
                return await result
            return result
        return await asyncio.to_thread(self._request_sync, method, path, body, prefer)

    def _request_sync(
        self,
        method: str,
        path: str,
        body: dict | None,
        prefer: str | None,
    ) -> Any:
        url = self.config.project_url.rstrip("/") + path
        payload = None
        if body is not None:
            payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.config.service_role_key}",
            "apikey": self.config.service_role_key,
            "Content-Type": "application/json",
        }
        if prefer is not None:
            headers["Prefer"] = prefer
        request = Request(
            url,
            data=payload,
            method=method,
            headers=headers,
        )
        try:
            with urlopen(request, timeout=15) as response:
                raw = response.read()
        except HTTPError as exc:
            if exc.code == 409:
                raise CloudStoreConflict("cloud row already exists") from exc
            raise RuntimeError(f"Supabase request failed with HTTP {exc.code}") from exc
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))


class CloudStoreConflict(RuntimeError):
    pass
