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

    The service-role key must never be shipped to browser/native clients. The
    adapter uses PostgREST so the relay process doesn't need a database driver.
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
    ) -> None:
        body: dict[str, Any] = {
            "id": run_id,
            "user_id": user_id,
            "device_id": device_id,
            "status": status,
        }
        if conversation_id is not None:
            body["conversation_id"] = conversation_id
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
        try:
            await self._request(
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
            return True
        except CloudStoreConflict:
            return False

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

    async def _request(
        self,
        method: str,
        path: str,
        body: dict,
        *,
        prefer: str,
    ) -> Any:
        if self._request_json_override is not None:
            result = self._request_json_override(method, path, body, prefer)
            if asyncio.iscoroutine(result):
                return await result
            return result
        return await asyncio.to_thread(self._request_sync, method, path, body, prefer)

    def _request_sync(self, method: str, path: str, body: dict, prefer: str) -> Any:
        url = self.config.project_url.rstrip("/") + path
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = Request(
            url,
            data=payload,
            method=method,
            headers={
                "Authorization": f"Bearer {self.config.service_role_key}",
                "apikey": self.config.service_role_key,
                "Content-Type": "application/json",
                "Prefer": prefer,
            },
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
