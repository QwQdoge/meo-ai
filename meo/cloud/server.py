from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from urllib.parse import urlencode, urlsplit

from meo.cloud.account_auth import (
    SupabaseAccountAuthConfig,
    SupabaseAccountTokenVerifier,
)
from meo.cloud.api import AgentRunApi, ApiError
from meo.cloud.device_auth import DeviceBearerVerifier
from meo.cloud.orchestrator import AgentRunOrchestrator
from meo.cloud.pairing import DevicePairingService
from meo.cloud.relay import RelayRegistry
from meo.cloud.routing import AutomaticDeviceResolver
from meo.cloud.store import SupabaseRestConfig, SupabaseRestStore
from meo.cloud.ws_server import RelayWebSocketServer


@dataclass(frozen=True)
class CloudServerConfig:
    supabase_url: str
    supabase_publishable_key: str
    supabase_service_role_key: str
    account_url: str = "https://account.meoarch.org"
    allowed_web_origins: tuple[str, ...] = ("https://account.meoarch.org",)
    bind_host: str = "127.0.0.1"
    port: int = 8080

    @classmethod
    def from_env(cls) -> "CloudServerConfig":
        def required(name: str) -> str:
            value = os.environ.get(name, "").strip()
            if not value:
                raise RuntimeError(f"{name} is required")
            return value

        port_text = os.environ.get("PORT", "8080").strip()
        try:
            port = int(port_text)
        except ValueError as exc:
            raise RuntimeError("PORT must be an integer") from exc
        if not (1 <= port <= 65535):
            raise RuntimeError("PORT must be between 1 and 65535")

        account_url = os.environ.get("MEO_ACCOUNT_URL", "https://account.meoarch.org").strip()
        account_origin = _normalized_origin(account_url, label="MEO_ACCOUNT_URL")
        configured_origins = os.environ.get("MEO_ALLOWED_WEB_ORIGINS", "").split(",")
        origins = [account_origin]
        for value in configured_origins:
            value = value.strip()
            if value:
                origins.append(_normalized_origin(value, label="MEO_ALLOWED_WEB_ORIGINS"))

        return cls(
            supabase_url=required("MEO_SUPABASE_URL"),
            supabase_publishable_key=required("MEO_SUPABASE_PUBLISHABLE_KEY"),
            supabase_service_role_key=required("MEO_SUPABASE_SERVICE_ROLE_KEY"),
            account_url=account_url.rstrip("/"),
            allowed_web_origins=tuple(dict.fromkeys(origins)),
            bind_host=os.environ.get("MEO_BIND_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=port,
        )


class _AiohttpRelaySocket:
    def __init__(self, request, websocket, ws_msg_type) -> None:
        self.request_headers = request.headers
        self.websocket = websocket
        self.ws_msg_type = ws_msg_type

    async def recv(self):
        message = await self.websocket.receive()
        if message.type == self.ws_msg_type.TEXT:
            return message.data
        if message.type == self.ws_msg_type.BINARY:
            return message.data
        if message.type in {
            self.ws_msg_type.CLOSE,
            self.ws_msg_type.CLOSED,
            self.ws_msg_type.CLOSING,
        }:
            raise ConnectionError("device relay disconnected")
        if message.type == self.ws_msg_type.ERROR:
            raise ConnectionError("device relay failed") from self.websocket.exception()
        raise ValueError("unsupported WebSocket frame")

    async def send(self, value: str) -> None:
        await self.websocket.send_str(value)


class _PairingStartLimiter:
    """Small in-process abuse guard for the unauthenticated pairing start route.

    Production should also rate-limit this endpoint at the reverse proxy/edge.
    X-Forwarded-For is deliberately ignored here because proxy trust belongs to
    deployment configuration, not application code.
    """

    def __init__(self, *, limit: int = 8, window_seconds: int = 600) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.entries: dict[str, list[float]] = {}

    def check(self, peer: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        recent = [stamp for stamp in self.entries.get(peer, ()) if stamp > cutoff]
        if len(recent) >= self.limit:
            raise ApiError(
                "rate_limited",
                "Too many device connection attempts. Try again later.",
                status=429,
            )
        recent.append(now)
        self.entries[peer] = recent


def _normalized_origin(value: str, *, label: str) -> str:
    parsed = urlsplit(value.strip())
    loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise RuntimeError(f"{label} must use https:// (http is allowed only for loopback development)")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError(f"{label} contains an invalid origin")
    if parsed.path not in {"", "/"}:
        raise RuntimeError(f"{label} must contain only an origin, not a path")
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = 443 if parsed.scheme == "https" else 80
    port = parsed.port
    authority = host if port in {None, default_port} else f"{host}:{port}"
    return f"{parsed.scheme}://{authority}"


def build_application(config: CloudServerConfig):
    try:
        from aiohttp import WSMsgType, web
    except ImportError as exc:
        raise RuntimeError(
            "Meo AI cloud service requires: pip install -r meo/cloud/requirements.txt"
        ) from exc

    store = SupabaseRestStore(
        SupabaseRestConfig(
            project_url=config.supabase_url,
            service_role_key=config.supabase_service_role_key,
        )
    )
    account_verifier = SupabaseAccountTokenVerifier(
        SupabaseAccountAuthConfig(
            project_url=config.supabase_url,
            publishable_key=config.supabase_publishable_key,
        )
    )
    device_verifier = DeviceBearerVerifier(store)
    pairing = DevicePairingService(store)
    pairing_limiter = _PairingStartLimiter()
    relay = RelayRegistry()
    resolver = AutomaticDeviceResolver(store=store, relay=relay)
    orchestrator = AgentRunOrchestrator(store=store, relay=relay, resolver=resolver)
    api = AgentRunApi(store=store, relay=relay, orchestrator=orchestrator)
    relay_server = RelayWebSocketServer(
        registry=relay,
        verifier=device_verifier,
        store=store,
    )
    allowed_origins = frozenset(config.allowed_web_origins)

    def apply_cors(request, response):
        origin = request.headers.get("Origin")
        if origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Max-Age"] = "600"
            response.headers["Vary"] = "Origin"
        return response

    @web.middleware
    async def safe_errors(request, handler):
        origin = request.headers.get("Origin")
        if origin and origin not in allowed_origins:
            return web.json_response(
                {"error": {"code": "origin_not_allowed", "message": "This web origin is not allowed."}},
                status=403,
                headers={"Cache-Control": "no-store", "Vary": "Origin"},
            )
        if request.method == "OPTIONS":
            if not origin:
                return web.Response(status=400, headers={"Cache-Control": "no-store"})
            requested_method = request.headers.get("Access-Control-Request-Method", "")
            if requested_method not in {"GET", "POST"}:
                return apply_cors(
                    request,
                    web.json_response(
                        {"error": {"code": "method_not_allowed", "message": "This request method is not allowed."}},
                        status=405,
                    ),
                )
            requested_headers = {
                item.strip().lower()
                for item in request.headers.get("Access-Control-Request-Headers", "").split(",")
                if item.strip()
            }
            if not requested_headers <= {"authorization", "content-type", "accept"}:
                return apply_cors(
                    request,
                    web.json_response(
                        {"error": {"code": "headers_not_allowed", "message": "This request header is not allowed."}},
                        status=400,
                    ),
                )
            return apply_cors(request, web.Response(status=204))

        try:
            response = await handler(request)
        except ApiError as exc:
            response = web.json_response(exc.as_dict(), status=exc.status)
        except LookupError:
            response = web.json_response(
                {"error": {"code": "not_found", "message": "This pairing request was not found."}},
                status=404,
            )
        except PermissionError:
            response = web.json_response(
                {"error": {"code": "not_allowed", "message": "This request is not allowed."}},
                status=403,
            )
        except ValueError as exc:
            response = web.json_response(
                {"error": {"code": "invalid_request", "message": str(exc)}},
                status=400,
            )
        except Exception:
            response = web.json_response(
                {"error": {"code": "internal_error", "message": "Meo AI could not complete this request."}},
                status=500,
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return apply_cors(request, response)

    app = web.Application(client_max_size=128 * 1024, middlewares=[safe_errors])

    async def identity(request):
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise ApiError("unauthorized", "Sign in with Meo Account.", status=401)
        token = authorization.removeprefix("Bearer ").strip()
        try:
            return await account_verifier.verify(token)
        except PermissionError as exc:
            raise ApiError(
                "unauthorized",
                "Your Meo Account session is invalid or expired.",
                status=401,
            ) from exc

    async def json_body(request) -> dict[str, Any]:
        if request.content_type != "application/json":
            raise ApiError("invalid_content_type", "Use application/json.", status=415)
        try:
            value = await request.json(loads=json.loads)
        except Exception as exc:
            raise ApiError("invalid_json", "Request body is not valid JSON.") from exc
        if not isinstance(value, dict):
            raise ApiError("invalid_request", "Request body must be an object.")
        return value

    def ensure_fields(payload: dict[str, Any], allowed: set[str]) -> None:
        unknown = set(payload) - allowed
        if unknown:
            raise ApiError(
                "unsupported_fields",
                "This request contains unsupported fields.",
                details={"fields": sorted(unknown)},
            )

    async def health(_request):
        return web.json_response({"ok": True, "service": "meo-ai-cloud"})

    def parse_conversation_id(request) -> str:
        try:
            return str(UUID(request.match_info["conversation_id"]))
        except (ValueError, TypeError, KeyError) as exc:
            raise ApiError("invalid_conversation_id", "Conversation ID is invalid.") from exc

    async def list_conversations(request):
        account = await identity(request)
        try:
            limit = int(request.query.get("limit", "50"))
        except ValueError as exc:
            raise ApiError("invalid_limit", "Conversation limit is invalid.") from exc
        if not 1 <= limit <= 100:
            raise ApiError("invalid_limit", "Conversation limit must be between 1 and 100.")
        rows = await store.list_conversations(user_id=account.user_id, limit=limit)
        return web.json_response({"conversations": list(rows)})

    async def create_conversation(request):
        account = await identity(request)
        payload = await json_body(request)
        ensure_fields(payload, {"title"})
        title = payload.get("title", "")
        if not isinstance(title, str) or len(title) > 200:
            raise ApiError("invalid_title", "Conversation title is invalid.")
        conversation = await store.create_conversation(
            user_id=account.user_id,
            title=title.strip(),
        )
        return web.json_response({"conversation": conversation}, status=201)

    async def list_conversation_messages(request):
        account = await identity(request)
        conversation_id = parse_conversation_id(request)
        conversation = await store.get_conversation(
            user_id=account.user_id,
            conversation_id=conversation_id,
        )
        if conversation is None:
            raise ApiError("conversation_not_found", "Conversation was not found.", status=404)
        rows = await store.list_conversation_messages(
            user_id=account.user_id,
            conversation_id=conversation_id,
        )
        return web.json_response({"messages": list(rows)})

    async def create_conversation_message(request):
        account = await identity(request)
        conversation_id = parse_conversation_id(request)
        payload = await json_body(request)
        ensure_fields(payload, {"role", "content"})
        role = payload.get("role")
        content = payload.get("content")
        if not isinstance(role, str) or role not in {"user", "assistant"}:
            raise ApiError("invalid_message_role", "Message role is invalid.")
        if not isinstance(content, str) or not content.strip() or len(content) > 40000:
            raise ApiError("invalid_message_content", "Message content is invalid.")
        conversation = await store.get_conversation(
            user_id=account.user_id,
            conversation_id=conversation_id,
        )
        if conversation is None:
            raise ApiError("conversation_not_found", "Conversation was not found.", status=404)
        message = await store.append_conversation_message(
            user_id=account.user_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        return web.json_response({"message": message}, status=201)

    async def start_device_pairing(request):
        pairing_limiter.check(request.remote or "unknown")
        payload = await json_body(request)
        ensure_fields(payload, {"device_id", "display_name", "capabilities"})
        capabilities = payload.get("capabilities")
        if not isinstance(capabilities, list) or any(not isinstance(item, str) for item in capabilities):
            raise ApiError("invalid_request", "capabilities must be a list of names.")
        started = await pairing.start(
            device_id=payload.get("device_id", ""),
            display_name=payload.get("display_name", ""),
            capabilities=capabilities,
        )
        query = urlencode({"code": started.user_code})
        return web.json_response(
            {
                "enrollment_id": started.enrollment_id,
                "user_code": started.user_code,
                "pairing_secret": started.pairing_secret,
                "verification_uri": f"{config.account_url}/connect-device",
                "verification_uri_complete": f"{config.account_url}/connect-device?{query}",
                "expires_at": started.expires_at.isoformat(),
                "poll_interval_seconds": 2,
            },
            status=201,
        )

    async def poll_device_pairing(request):
        payload = await json_body(request)
        ensure_fields(payload, {"pairing_secret"})
        secret = payload.get("pairing_secret")
        if not isinstance(secret, str):
            raise ApiError("invalid_request", "pairing_secret is required.")
        result = await pairing.poll(pairing_secret=secret)
        body: dict[str, Any] = {"state": result.state}
        if result.device_token is not None:
            body.update(
                {
                    "device_token": result.device_token,
                    "device_id": result.device_id,
                    "expires_at": result.expires_at.isoformat() if result.expires_at else None,
                }
            )
        return web.json_response(body)

    async def preview_device_pairing(request):
        await identity(request)
        preview = await pairing.preview(user_code=request.match_info["user_code"])
        return web.json_response(
            {
                "user_code": preview.user_code,
                "device_id": preview.device_id,
                "display_name": preview.display_name,
                "capabilities": list(preview.capabilities),
                "expires_at": preview.expires_at.isoformat(),
            }
        )

    async def approve_device_pairing(request):
        account = await identity(request)
        try:
            preview = await pairing.approve(
                identity=account,
                user_code=request.match_info["user_code"],
            )
        except PermissionError as exc:
            message = str(exc)
            if "verification is required" in message or "cannot approve" in message:
                raise ApiError(
                    "reauth_required",
                    "Verify your Meo Account to connect this device.",
                    status=403,
                    details={"purpose": "account_security"},
                ) from exc
            raise
        return web.json_response(
            {"state": "approved", "device_id": preview.device_id, "display_name": preview.display_name}
        )

    async def create_agent_run(request):
        account = await identity(request)
        payload = await json_body(request)
        result = await api.create(
            user_id=account.user_id,
            payload=payload,
            allow_full_access=False,
        )
        return web.json_response(result, status=201)

    async def cancel_agent_run(request):
        account = await identity(request)
        result = await api.cancel(user_id=account.user_id, run_id=request.match_info["run_id"])
        return web.json_response(result)

    async def decide_agent_run(request):
        account = await identity(request)
        payload = await json_body(request)
        ensure_fields(payload, {"option_index"})
        result = await api.decide(
            user_id=account.user_id,
            run_id=request.match_info["run_id"],
            decision_id=request.match_info["decision_id"],
            option_index=payload.get("option_index"),
        )
        return web.json_response(result)

    async def agent_run_events(request):
        account = await identity(request)
        run_id = request.query.get("run_id", "").strip()
        try:
            after = int(request.query.get("after", "-1"))
        except ValueError as exc:
            raise ApiError("invalid_cursor", "after must be an integer >= -1.") from exc
        if not run_id or after < -1:
            raise ApiError("invalid_request", "run_id and an event cursor >= -1 are required.")
        run = await store.get_agent_run(user_id=account.user_id, run_id=run_id)
        if run is None:
            raise ApiError("run_not_found", "Agent task not found.", status=404)
        response = web.StreamResponse(headers={
            "Content-Type": "text/event-stream", "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff", "X-Accel-Buffering": "no",
        })
        apply_cors(request, response)
        await response.prepare(request)
        try:
            # Bound each connection; the client resumes the same run/cursor.
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                rows = await store.list_agent_events(user_id=account.user_id, run_id=run_id, after=after)
                for row in rows:
                    seq = row["seq"]
                    if seq != after + 1:
                        await response.write(b'event: error\ndata: {"code":"event_gap"}\n\n')
                        return response
                    data = json.dumps(row["payload"], separators=(",", ":"))
                    frame = f'id: {seq}\nevent: {row["event_type"]}\ndata: {data}\n\n'
                    await response.write(frame.encode("utf-8"))
                    after = seq
                run = await store.get_agent_run(user_id=account.user_id, run_id=run_id)
                if run is None or (run.get("status") in {"completed", "cancelled", "failed"}
                                   and after >= run.get("last_event_seq", -1) and len(rows) < 100):
                    break
                if not rows:
                    await response.write(b": keepalive\n\n")
                    await asyncio.sleep(0.25)
        except (ConnectionError, asyncio.CancelledError):
            # Disconnecting an event subscriber never cancels or resubmits work.
            raise
        return response

    async def device_relay(request):
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise ApiError("unauthorized_device", "Device credential is required.", status=401)
        token = authorization.removeprefix("Bearer ").strip()
        try:
            claims = await device_verifier.verify(token)
        except PermissionError as exc:
            raise ApiError(
                "unauthorized_device",
                "Device credential is invalid or expired.",
                status=401,
            ) from exc
        if not claims.allows("relay.connect"):
            raise ApiError(
                "unauthorized_device",
                "Device credential cannot connect to Relay.",
                status=403,
            )

        requested_protocols = request.headers.get("Sec-WebSocket-Protocol", "")
        protocols = {item.strip() for item in requested_protocols.split(",") if item.strip()}
        if "meo-agentd.v1" not in protocols:
            raise ApiError("unsupported_protocol", "meo-agentd.v1 is required.", status=426)

        websocket = web.WebSocketResponse(
            protocols=("meo-agentd.v1",),
            heartbeat=20,
            receive_timeout=None,
            max_msg_size=1_048_576,
        )
        await websocket.prepare(request)
        adapter = _AiohttpRelaySocket(request, websocket, WSMsgType)
        try:
            await relay_server.handle(adapter, claims=claims)
        except ConnectionError:
            pass
        finally:
            if not websocket.closed:
                await websocket.close()
        return websocket

    app.add_routes(
        [
            web.get("/health", health),
            web.get("/v1/conversations", list_conversations),
            web.post("/v1/conversations", create_conversation),
            web.get(
                "/v1/conversations/{conversation_id}/messages",
                list_conversation_messages,
            ),
            web.post(
                "/v1/conversations/{conversation_id}/messages",
                create_conversation_message,
            ),
            web.post("/v1/device-enrollments/start", start_device_pairing),
            web.post("/v1/device-enrollments/poll", poll_device_pairing),
            web.get("/v1/device-enrollments/{user_code}", preview_device_pairing),
            web.post("/v1/device-enrollments/{user_code}/approve", approve_device_pairing),
            web.post("/v1/agent-runs", create_agent_run),
            web.get("/v1/agent-runs/events", agent_run_events),
            web.post("/v1/agent-runs/{run_id}/cancel", cancel_agent_run),
            web.post(
                "/v1/agent-runs/{run_id}/decisions/{decision_id}",
                decide_agent_run,
            ),
            web.get("/v1/device-relay", device_relay),
        ]
    )
    return app


def main() -> None:
    try:
        from aiohttp import web
    except ImportError as exc:
        raise SystemExit(
            "Install cloud dependencies with: pip install -r meo/cloud/requirements.txt"
        ) from exc

    config = CloudServerConfig.from_env()
    app = build_application(config)
    web.run_app(app, host=config.bind_host, port=config.port, access_log=None)


if __name__ == "__main__":
    main()
