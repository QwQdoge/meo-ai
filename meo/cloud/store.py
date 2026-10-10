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
    async def list_conversations(
        self, *, user_id: str, limit: int = 50,
    ) -> tuple[dict, ...]: ...

    async def create_conversation(self, *, user_id: str, title: str) -> dict: ...

    async def get_conversation(self, *, user_id: str, conversation_id: str) -> dict | None: ...

    async def list_conversation_messages(
        self, *, user_id: str, conversation_id: str, limit: int = 500,
    ) -> tuple[dict, ...]: ...

    async def append_conversation_message(
        self, *, user_id: str, conversation_id: str, role: str, content: str,
    ) -> dict: ...

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
    opaque credential/enrollment lookups use only one-way token hashes or short
    public pairing codes.
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

    async def list_conversations(
        self, *, user_id: str, limit: int = 50,
    ) -> tuple[dict, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("conversation limit must be between 1 and 100")
        query = urlencode(
            {
                "select": "id,title,created_at,updated_at",
                "user_id": f"eq.{user_id}",
                "order": "updated_at.desc,id.desc",
                "limit": str(limit),
            }
        )
        result = await self._request("GET", f"/rest/v1/ai_conversations?{query}", None)
        if not isinstance(result, list):
            raise RuntimeError("Supabase conversation response is invalid")
        return tuple(row for row in result if isinstance(row, dict))

    async def create_conversation(self, *, user_id: str, title: str) -> dict:
        result = await self._request(
            "POST",
            "/rest/v1/ai_conversations",
            {"user_id": user_id, "title": title.strip()[:200]},
            prefer="return=representation",
        )
        row = self._single_row(result, "Supabase conversation creation response is invalid")
        if row is None:
            raise RuntimeError("Supabase did not create a conversation")
        return row

    async def get_conversation(
        self, *, user_id: str, conversation_id: str,
    ) -> dict | None:
        query = urlencode(
            {
                "select": "id,title,created_at,updated_at",
                "id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
                "limit": "1",
            }
        )
        result = await self._request("GET", f"/rest/v1/ai_conversations?{query}", None)
        return self._single_row(result, "Supabase conversation response is invalid")

    async def list_conversation_messages(
        self, *, user_id: str, conversation_id: str, limit: int = 500,
    ) -> tuple[dict, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("message limit must be between 1 and 1000")
        query = urlencode(
            {
                "select": "id,conversation_id,role,executor,content,created_at",
                "conversation_id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
                "order": "created_at.asc,id.asc",
                "limit": str(limit),
            }
        )
        result = await self._request("GET", f"/rest/v1/ai_messages?{query}", None)
        if not isinstance(result, list):
            raise RuntimeError("Supabase message response is invalid")
        return tuple(row for row in result if isinstance(row, dict))

    async def append_conversation_message(
        self, *, user_id: str, conversation_id: str, role: str, content: str,
    ) -> dict:
        if role not in {"user", "assistant"}:
            raise ValueError("message role is invalid")
        result = await self._request(
            "POST",
            "/rest/v1/ai_messages",
            {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "role": role,
                "executor": "chat",
                "content": [{"type": "text", "text": content}],
            },
            prefer="return=representation",
        )
        row = self._single_row(result, "Supabase message creation response is invalid")
        if row is None:
            raise RuntimeError("Supabase did not create a message")
        now = datetime.now(timezone.utc).isoformat()
        query = urlencode(
            {
                "id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
            }
        )
        await self._request(
            "PATCH",
            f"/rest/v1/ai_conversations?{query}",
            {"updated_at": now},
            prefer="return=minimal",
        )
        return row

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
        result = await self._request("GET", f"/rest/v1/ai_project_locations?{query}", None)
        if not isinstance(result, list):
            raise RuntimeError("Supabase project location response is invalid")
        rows: list[dict] = []
        for row in result:
            if not isinstance(row, dict):
                continue
            device_id = row.get("device_id")
            workspace_ref = row.get("workspace_ref")
            if isinstance(device_id, str) and device_id.strip() and isinstance(workspace_ref, str) and workspace_ref.strip():
                rows.append({"device_id": device_id.strip(), "workspace_ref": workspace_ref.strip()})
        return tuple(rows)

    async def get_agent_run(self, *, user_id: str, run_id: str) -> dict | None:
        query = urlencode(
            {
                "select": "id,device_id,status,conversation_id,permission_mode,last_event_seq",
                "id": f"eq.{run_id}",
                "user_id": f"eq.{user_id}",
                "limit": "1",
            }
        )
        result = await self._request("GET", f"/rest/v1/ai_agent_runs?{query}", None)
        return self._single_row(result, "Supabase AgentRun response is invalid")

    async def list_agent_events(
        self, *, user_id: str, run_id: str, after: int, limit: int = 100,
    ) -> tuple[dict, ...]:
        if not isinstance(after, int) or isinstance(after, bool) or after < -1:
            raise ValueError("event cursor must be >= -1")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("event limit must be between 1 and 100")
        query = urlencode({
            "select": "seq,event_type,payload", "user_id": f"eq.{user_id}",
            "run_id": f"eq.{run_id}", "seq": f"gt.{after}",
            "order": "seq.asc", "limit": str(limit),
        })
        result = await self._request("GET", f"/rest/v1/ai_agent_events?{query}", None)
        if not isinstance(result, list) or any(not isinstance(row, dict) for row in result):
            raise RuntimeError("Supabase AgentRun events response is invalid")
        return tuple(result)

    async def get_device_credential_by_hash(self, *, token_hash: str) -> dict | None:
        token_hash = self._sha256_hex(token_hash)
        query = urlencode(
            {
                "select": "id,user_id,device_id,scopes,issued_at,expires_at,revoked_at",
                "token_hash": f"eq.{token_hash}",
                "limit": "1",
            }
        )
        result = await self._request("GET", f"/rest/v1/ai_device_credentials?{query}", None)
        return self._single_row(result, "Supabase device credential response is invalid")

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
    ) -> None:
        self._sha256_hex(secret_hash)
        if not user_code or len(user_code) != 8:
            raise ValueError("user_code must be 8 characters")
        if not device_id.strip() or not display_name.strip():
            raise ValueError("device identity is required")
        if not capabilities or not requested_scopes:
            raise ValueError("enrollment capabilities and scopes are required")
        if expires_at.tzinfo is None or expires_at <= datetime.now(timezone.utc):
            raise ValueError("enrollment expiry must be in the future")
        await self._request(
            "POST",
            "/rest/v1/ai_device_enrollments",
            {
                "id": enrollment_id,
                "secret_hash": secret_hash,
                "user_code": user_code,
                "device_id": device_id.strip(),
                "display_name": display_name.strip(),
                "capabilities": list(capabilities),
                "requested_scopes": list(requested_scopes),
                "expires_at": expires_at.isoformat(),
            },
            prefer="return=minimal",
        )

    async def get_device_enrollment_by_code(self, *, user_code: str) -> dict | None:
        query = urlencode(
            {
                "select": "id,user_id,device_id,display_name,capabilities,requested_scopes,state,expires_at,approved_at,consumed_at",
                "user_code": f"eq.{user_code.strip().upper()}",
                "limit": "1",
            }
        )
        result = await self._request("GET", f"/rest/v1/ai_device_enrollments?{query}", None)
        return self._single_row(result, "Supabase enrollment response is invalid")

    async def get_device_enrollment_by_secret_hash(self, *, secret_hash: str) -> dict | None:
        secret_hash = self._sha256_hex(secret_hash)
        query = urlencode(
            {
                "select": "id,user_id,device_id,display_name,capabilities,requested_scopes,state,expires_at,approved_at,consumed_at",
                "secret_hash": f"eq.{secret_hash}",
                "limit": "1",
            }
        )
        result = await self._request("GET", f"/rest/v1/ai_device_enrollments?{query}", None)
        return self._single_row(result, "Supabase enrollment response is invalid")

    async def approve_device_enrollment(
        self,
        *,
        enrollment_id: str,
        user_id: str,
    ) -> dict | None:
        now = datetime.now(timezone.utc)
        query = urlencode(
            {
                "id": f"eq.{enrollment_id}",
                "state": "eq.pending",
                "expires_at": f"gt.{now.isoformat()}",
            }
        )
        result = await self._request(
            "PATCH",
            f"/rest/v1/ai_device_enrollments?{query}",
            {
                "user_id": user_id,
                "state": "approved",
                "approved_at": now.isoformat(),
            },
            prefer="return=representation",
        )
        return self._single_row(result, "Supabase enrollment approval response is invalid")

    async def consume_device_enrollment(
        self,
        *,
        secret_hash: str,
        token_hash: str,
        credential_expires_at: datetime,
    ) -> dict | None:
        secret_hash = self._sha256_hex(secret_hash)
        token_hash = self._sha256_hex(token_hash)
        if credential_expires_at.tzinfo is None or credential_expires_at <= datetime.now(timezone.utc):
            raise ValueError("credential expiry must be in the future")
        result = await self._request(
            "POST",
            "/rest/v1/rpc/service_consume_ai_device_enrollment",
            {
                "target_secret_hash": secret_hash,
                "new_token_hash": token_hash,
                "credential_expires_at": credential_expires_at.isoformat(),
            },
            prefer="return=representation",
        )
        return self._single_row(result, "Supabase enrollment consumption response is invalid")

    async def has_recent_reauth(
        self,
        *,
        user_id: str,
        session_id: str,
        purpose: str,
    ) -> bool:
        if purpose not in {"account_security", "admin"}:
            raise ValueError("unsupported reauth purpose")
        now = datetime.now(timezone.utc).isoformat()
        query = urlencode(
            {
                "select": "expires_at",
                "user_id": f"eq.{user_id}",
                "session_id": f"eq.{session_id}",
                "purpose": f"eq.{purpose}",
                "expires_at": f"gt.{now}",
                "limit": "1",
            }
        )
        result = await self._request("GET", f"/rest/v1/reauth_grants?{query}", None)
        if not isinstance(result, list):
            raise RuntimeError("Supabase re-auth response is invalid")
        return bool(result)

    @staticmethod
    def _single_row(result: Any, error_message: str) -> dict | None:
        if not isinstance(result, list):
            raise RuntimeError(error_message)
        if not result:
            return None
        row = result[0]
        return row if isinstance(row, dict) else None

    @staticmethod
    def _sha256_hex(value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError("value must be a SHA-256 hex digest")
        return normalized

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
        request = Request(url, data=payload, method=method, headers=headers)
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
