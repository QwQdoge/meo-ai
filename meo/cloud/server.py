from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from meo.cloud.account_auth import (
    SupabaseAccountAuthConfig,
    SupabaseAccountTokenVerifier,
)
from meo.cloud.api import AgentRunApi, ApiError
from meo.cloud.device_auth import DeviceBearerVerifier
from meo.cloud.orchestrator import AgentRunOrchestrator
from meo.cloud.relay import RelayRegistry
from meo.cloud.routing import AutomaticDeviceResolver
from meo.cloud.store import SupabaseRestConfig, SupabaseRestStore
from meo.cloud.ws_server import RelayWebSocketServer


@dataclass(frozen=True)
class CloudServerConfig:
    supabase_url: str
    supabase_publishable_key: str
    supabase_service_role_key: str
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

        return cls(
            supabase_url=required("MEO_SUPABASE_URL"),
            supabase_publishable_key=required("MEO_SUPABASE_PUBLISHABLE_KEY"),
            supabase_service_role_key=required("MEO_SUPABASE_SERVICE_ROLE_KEY"),
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
    relay = RelayRegistry()
    resolver = AutomaticDeviceResolver(store=store, relay=relay)
    orchestrator = AgentRunOrchestrator(store=store, relay=relay, resolver=resolver)
    api = AgentRunApi(store=store, relay=relay, orchestrator=orchestrator)
    relay_server = RelayWebSocketServer(
        registry=relay,
        verifier=device_verifier,
        store=store,
    )

    @web.middleware
    async def safe_errors(request, handler):
        try:
            response = await handler(request)
        except ApiError as exc:
            return web.json_response(exc.as_dict(), status=exc.status)
        except PermissionError:
            return web.json_response(
                {"error": {"code": "not_allowed", "message": "This request is not allowed."}},
                status=403,
            )
        except ValueError as exc:
            return web.json_response(
                {"error": {"code": "invalid_request", "message": str(exc)}},
                status=400,
            )
        except Exception:
            # Never leak stack traces, local paths, database payloads or secrets.
            return web.json_response(
                {"error": {"code": "internal_error", "message": "Meo AI could not complete this request."}},
                status=500,
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    app = web.Application(
        client_max_size=128 * 1024,
        middlewares=[safe_errors],
    )

    async def identity(request):
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise ApiError("unauthorized", "Sign in with Meo Account.", status=401)
        token = authorization.removeprefix("Bearer ").strip()
        try:
            return await account_verifier.verify(token)
        except PermissionError as exc:
            raise ApiError("unauthorized", "Your Meo Account session is invalid or expired.", status=401) from exc

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

    async def health(_request):
        return web.json_response({"ok": True, "service": "meo-ai-cloud"})

    async def create_agent_run(request):
        account = await identity(request)
        payload = await json_body(request)
        result = await api.create(
            user_id=account.user_id,
            payload=payload,
            # Full Access stays disabled until a trusted Account re-auth adapter
            # explicitly authorizes this request server-side.
            allow_full_access=False,
        )
        return web.json_response(result, status=201)

    async def cancel_agent_run(request):
        account = await identity(request)
        result = await api.cancel(
            user_id=account.user_id,
            run_id=request.match_info["run_id"],
        )
        return web.json_response(result)

    async def decide_agent_run(request):
        account = await identity(request)
        payload = await json_body(request)
        allowed = {"option_index"}
        unknown = set(payload) - allowed
        if unknown:
            raise ApiError(
                "unsupported_fields",
                "This decision contains unsupported fields.",
                details={"fields": sorted(unknown)},
            )
        result = await api.decide(
            user_id=account.user_id,
            run_id=request.match_info["run_id"],
            decision_id=request.match_info["decision_id"],
            option_index=payload.get("option_index"),
        )
        return web.json_response(result)

    async def device_relay(request):
        # Reject invalid device credentials before sending HTTP 101 Upgrade.
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise ApiError("unauthorized_device", "Device credential is required.", status=401)
        token = authorization.removeprefix("Bearer ").strip()
        try:
            claims = await device_verifier.verify(token)
        except PermissionError as exc:
            raise ApiError("unauthorized_device", "Device credential is invalid or expired.", status=401) from exc
        if not claims.allows("relay.connect"):
            raise ApiError("unauthorized_device", "Device credential cannot connect to Relay.", status=403)

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
            web.post("/v1/agent-runs", create_agent_run),
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
    # TLS is intentionally terminated by the deployment platform/reverse proxy.
    # Do not expose this bind directly to the public internet without HTTPS.
    web.run_app(app, host=config.bind_host, port=config.port, access_log=None)


if __name__ == "__main__":
    main()
