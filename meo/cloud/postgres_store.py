from __future__ import annotations

import json
import ssl
from datetime import datetime, timezone
from typing import Any


class NeonPostgresStore:
    """Neon/PostgreSQL implementation of the Meo AI cloud persistence contract."""

    def __init__(self, database_url: str, *, pool: Any | None = None) -> None:
        if not database_url.startswith(("postgres://", "postgresql://")):
            raise ValueError("MEO_DATABASE_URL must be a PostgreSQL connection URL")
        self._database_url = database_url
        self._pool = pool

    async def _get_pool(self):
        if self._pool is None:
            try:
                import asyncpg
            except ImportError as exc:
                raise RuntimeError("Neon persistence requires asyncpg") from exc

            async def initialize(connection):
                await connection.set_type_codec(
                    "json", schema="pg_catalog", encoder=json.dumps, decoder=json.loads,
                )
                await connection.set_type_codec(
                    "jsonb", schema="pg_catalog", encoder=json.dumps, decoder=json.loads,
                )

            self._pool = await asyncpg.create_pool(
                dsn=self._database_url,
                ssl=ssl.create_default_context(),
                server_settings={"role": "meo_ai_limited"},
                min_size=1,
                max_size=10,
                command_timeout=15,
                init=initialize,
            )
        return self._pool

    @staticmethod
    def _rows(records) -> tuple[dict, ...]:
        return tuple(dict(row) for row in records)

    async def list_conversations(self, *, user_id: str, limit: int = 50, before=None):
        if not 1 <= limit <= 101:
            raise ValueError("conversation limit must be between 1 and 101")
        pool = await self._get_pool()
        if before is None:
            rows = await pool.fetch(
                """select id::text, title, created_at, updated_at from ai_conversations
                   where user_id = $1::uuid order by updated_at desc, id desc limit $2""",
                user_id, limit,
            )
        else:
            updated_at, conversation_id = before
            rows = await pool.fetch(
                """select id::text, title, created_at, updated_at from ai_conversations
                   where user_id = $1::uuid and (updated_at, id) < ($2::timestamptz, $3::uuid)
                   order by updated_at desc, id desc limit $4""",
                user_id, updated_at, conversation_id, limit,
            )
        return self._rows(rows)

    async def create_conversation(self, *, user_id: str, title: str) -> dict:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            """insert into ai_conversations(user_id,title) values($1::uuid,$2)
               returning id::text,title,created_at,updated_at""",
            user_id, title.strip()[:200],
        )
        return dict(row)

    async def get_conversation(self, *, user_id: str, conversation_id: str) -> dict | None:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            """select id::text,title,created_at,updated_at from ai_conversations
               where id=$1::uuid and user_id=$2::uuid""", conversation_id, user_id,
        )
        return dict(row) if row else None

    async def list_conversation_messages(self, *, user_id: str, conversation_id: str, limit: int = 500):
        if not 1 <= limit <= 1000:
            raise ValueError("message limit must be between 1 and 1000")
        pool = await self._get_pool()
        rows = await pool.fetch(
            """select m.id::text,m.conversation_id::text,m.role,m.executor,m.content,m.created_at
               from ai_messages m join ai_conversations c on c.id=m.conversation_id
               where c.user_id=$1::uuid and m.user_id=$1::uuid and c.id=$2::uuid
               order by m.created_at asc,m.id asc limit $3""",
            user_id, conversation_id, limit,
        )
        return self._rows(rows)

    async def append_conversation_message(self, *, user_id: str, conversation_id: str, role: str, content: str) -> dict:
        if role not in {"user", "assistant"}:
            raise ValueError("message role is invalid")
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                owned = await connection.fetchval(
                    "select id from ai_conversations where id=$1::uuid and user_id=$2::uuid for update",
                    conversation_id, user_id,
                )
                if owned is None:
                    raise LookupError("conversation_not_found")
                row = await connection.fetchrow(
                    """insert into ai_messages(user_id,conversation_id,role,executor,content)
                       values($1::uuid,$2::uuid,$3,'chat',$4::jsonb)
                       returning id::text,conversation_id::text,role,executor,content,created_at""",
                    user_id, conversation_id, role,
                    [{"type": "text", "text": content}],
                )
                await connection.execute("update ai_conversations set updated_at=now() where id=$1::uuid", conversation_id)
                return dict(row)

    async def touch_device(self, *, user_id: str, device_id: str, display_name: str, capabilities: tuple[str, ...]) -> None:
        pool = await self._get_pool()
        await pool.execute(
            """insert into ai_devices(user_id,device_id,display_name,capabilities,last_seen_at,updated_at)
               values($1::uuid,$2,$3,$4,now(),now())
               on conflict(user_id,device_id) do update set display_name=excluded.display_name,
                 capabilities=excluded.capabilities,last_seen_at=now(),updated_at=now()""",
            user_id, device_id, display_name, list(capabilities),
        )

    async def create_agent_run(self, *, run_id: str, user_id: str, conversation_id: str | None,
                               device_id: str, status: str, project_id: str | None = None,
                               workspace_ref: str | None = None, permission_mode: str = "smart",
                               requested_capabilities: tuple[str, ...] = ("agent.chat",)) -> None:
        if permission_mode not in {"ask", "smart", "full_access"} or not requested_capabilities:
            raise ValueError("invalid AgentRun policy")
        pool = await self._get_pool()
        await pool.execute(
            """insert into ai_agent_runs(id,user_id,conversation_id,device_id,status,project_id,
                   workspace_ref,permission_mode,requested_capabilities)
               values($1::uuid,$2::uuid,$3::uuid,$4,$5,$6::uuid,$7,$8,$9)
               on conflict(id) do nothing""",
            run_id,user_id,conversation_id,device_id,status,project_id,workspace_ref,
            permission_mode,list(requested_capabilities),
        )

    async def append_agent_event(self, *, user_id: str, run_id: str, seq: int, event_type: str, payload: dict) -> bool:
        if not isinstance(seq,int) or isinstance(seq,bool) or seq < 0 or not event_type.strip():
            raise ValueError("invalid AgentRun event")
        pool = await self._get_pool()
        result = await pool.execute(
            """insert into ai_agent_events(user_id,run_id,seq,event_type,payload)
               values($1::uuid,$2::uuid,$3,$4,$5::jsonb) on conflict(run_id,seq) do nothing""",
            user_id,run_id,seq,event_type,payload,
        )
        return result.endswith(" 1")

    async def update_agent_run(self, *, user_id: str, run_id: str, values: dict) -> None:
        allowed = {"status","local_request_id","last_event_seq","error_code","started_at","finished_at","updated_at"}
        if set(values) - allowed:
            raise ValueError("unsupported AgentRun fields")
        values = dict(values)
        values.setdefault("updated_at", datetime.now(timezone.utc))
        # Event frames can arrive late after a reconnect. Cursor updates
        # must be monotonic even when another relay handler raced ahead.
        assignments = ",".join(
            f"{key}=greatest(coalesce(last_event_seq,-1),${index})"
            if key == "last_event_seq" else f"{key}=${index}"
            for index,key in enumerate(values,1)
        )
        params = list(values.values()) + [run_id,user_id]
        pool = await self._get_pool()
        await pool.execute(f"update ai_agent_runs set {assignments} where id=${len(values)+1}::uuid and user_id=${len(values)+2}::uuid",*params)

    async def list_project_locations(self, *, user_id: str, project_id: str):
        pool = await self._get_pool()
        rows = await pool.fetch(
            """select device_id,workspace_ref from ai_project_locations where user_id=$1::uuid
               and project_id=$2::uuid order by updated_at desc""", user_id,project_id,
        )
        return self._rows(rows)

    async def list_agent_runs(self, *, user_id: str, limit: int = 30) -> tuple[dict, ...]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
            raise ValueError("AgentRun list limit must be between 1 and 50")
        pool = await self._get_pool()
        rows = await pool.fetch(
            """select id::text,device_id,conversation_id::text,project_id::text,
                      status,permission_mode,last_event_seq,created_at,updated_at,finished_at
               from ai_agent_runs where user_id=$1::uuid
               order by created_at desc,id desc limit $2""",
            user_id, limit,
        )
        return self._rows(rows)

    async def get_agent_run(self, *, user_id: str, run_id: str) -> dict | None:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            """select id::text,device_id,status,conversation_id::text,project_id::text,
                      permission_mode,last_event_seq,created_at,updated_at,finished_at
               from ai_agent_runs where id=$1::uuid and user_id=$2::uuid""", run_id,user_id,
        )
        return dict(row) if row else None

    async def list_agent_events(self, *, user_id: str, run_id: str, after: int, limit: int = 100):
        if not isinstance(after,int) or isinstance(after,bool) or after < -1 or not 1 <= limit <= 100:
            raise ValueError("invalid AgentRun event cursor")
        pool = await self._get_pool()
        rows = await pool.fetch(
            """select seq,event_type,payload from ai_agent_events where user_id=$1::uuid
               and run_id=$2::uuid and seq>$3 order by seq asc limit $4""",
            user_id,run_id,after,limit,
        )
        return self._rows(rows)

    async def get_device_credential_by_hash(self, *, token_hash: str) -> dict | None:
        self._sha256_hex(token_hash)
        pool = await self._get_pool()
        row = await pool.fetchrow(
            """select id::text,user_id::text,device_id,scopes,issued_at,expires_at,revoked_at
               from ai_device_credentials where token_hash=$1""", token_hash.lower(),
        )
        return dict(row) if row else None

    async def create_device_enrollment(self, *, enrollment_id: str, secret_hash: str, user_code: str,
                                       device_id: str, display_name: str, capabilities: tuple[str,...],
                                       requested_scopes: tuple[str,...], expires_at: datetime) -> None:
        self._sha256_hex(secret_hash)
        if len(user_code) != 8 or not device_id.strip() or not display_name.strip() or not capabilities or not requested_scopes:
            raise ValueError("invalid device enrollment")
        if expires_at.tzinfo is None or expires_at <= datetime.now(timezone.utc):
            raise ValueError("enrollment expiry must be in the future")
        pool = await self._get_pool()
        await pool.execute(
            """insert into ai_device_enrollments(id,secret_hash,user_code,device_id,display_name,
               capabilities,requested_scopes,expires_at) values($1::uuid,$2,$3,$4,$5,$6,$7,$8)""",
            enrollment_id,secret_hash.lower(),user_code.upper(),device_id.strip(),display_name.strip(),
            list(capabilities),list(requested_scopes),expires_at,
        )

    async def get_device_enrollment_by_code(self, *, user_code: str) -> dict | None:
        return await self._get_enrollment("user_code", user_code.strip().upper())

    async def get_device_enrollment_by_secret_hash(self, *, secret_hash: str) -> dict | None:
        self._sha256_hex(secret_hash)
        return await self._get_enrollment("secret_hash", secret_hash.lower())

    async def _get_enrollment(self, field: str, value: str) -> dict | None:
        if field not in {"user_code","secret_hash"}:
            raise ValueError("invalid enrollment lookup")
        pool = await self._get_pool()
        row = await pool.fetchrow(
            f"""select id::text,user_id::text,device_id,display_name,capabilities,requested_scopes,
                state,expires_at,approved_at,consumed_at from ai_device_enrollments where {field}=$1""", value,
        )
        return dict(row) if row else None

    async def approve_device_enrollment(self, *, enrollment_id: str, user_id: str) -> dict | None:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            """update ai_device_enrollments set user_id=$2::uuid,state='approved',approved_at=now()
               where id=$1::uuid and state='pending' and expires_at>now()
               returning id::text,user_id::text,device_id,display_name,capabilities,requested_scopes,
                         state,expires_at,approved_at,consumed_at""", enrollment_id,user_id,
        )
        return dict(row) if row else None

    async def consume_device_enrollment(self, *, secret_hash: str, token_hash: str, credential_expires_at: datetime) -> dict | None:
        self._sha256_hex(secret_hash); self._sha256_hex(token_hash)
        if credential_expires_at.tzinfo is None or credential_expires_at <= datetime.now(timezone.utc):
            raise ValueError("credential expiry must be in the future")
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                enrollment = await connection.fetchrow(
                    """select * from ai_device_enrollments where secret_hash=$1 for update""",secret_hash.lower(),
                )
                if not enrollment or enrollment["state"] != "approved" or not enrollment["user_id"] or enrollment["expires_at"] <= datetime.now(timezone.utc) or credential_expires_at <= datetime.now(timezone.utc):
                    return None
                await connection.execute(
                    """insert into ai_devices(user_id,device_id,display_name,capabilities,last_seen_at,updated_at)
                       values($1,$2,$3,$4,now(),now()) on conflict(user_id,device_id) do update set
                       display_name=excluded.display_name,capabilities=excluded.capabilities,revoked_at=null,updated_at=now()""",
                    enrollment["user_id"],enrollment["device_id"],enrollment["display_name"],enrollment["capabilities"],
                )
                credential = await connection.fetchrow(
                    """insert into ai_device_credentials(user_id,device_id,token_hash,scopes,expires_at)
                       values($1,$2,$3,$4,$5) returning id""",
                    enrollment["user_id"],enrollment["device_id"],token_hash.lower(),enrollment["requested_scopes"],credential_expires_at,
                )
                await connection.execute(
                    """update ai_device_enrollments set state='consumed',credential_id=$2,consumed_at=now()
                       where id=$1""", enrollment["id"],credential["id"],
                )
                return {"account_user_id":str(enrollment["user_id"]),"device_id":enrollment["device_id"],
                        "credential_id":str(credential["id"]),"scopes":list(enrollment["requested_scopes"])}

    async def has_recent_reauth(self, *, user_id: str, session_id: str, purpose: str) -> bool:
        if purpose not in {"account_security","admin"}:
            raise ValueError("unsupported reauth purpose")
        # Account owns grants in its separate database. The compatibility AI
        # service must never consult a lookalike grant table or accept a client flag.
        # Browser approval is performed through Meo API's Account-backed endpoint.
        return False

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @staticmethod
    def _sha256_hex(value: str) -> None:
        normalized=value.strip().lower()
        if len(normalized)!=64 or any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError("value must be a SHA-256 hex digest")
