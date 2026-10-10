from __future__ import annotations

import socket
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from meo.runtime.http_transport import AgentHttpTransport, _Handler
from meo.service.core import AgentServiceCore


class _NativeHandler(_Handler):
    """Native-client compatibility routes kept at the loopback transport edge.

    AgentService's canonical managed-memory API currently uses `/v1/memories`
    plus `/v1/memory/state`. The native product surface deliberately treats
    memory as one resource (`/v1/memory`) and expects state + records together.
    Keep that presentation alias here instead of leaking duplicate semantics
    into AgentServiceCore or the memory backend.
    """

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/v1/memory":
            super().do_GET()
            return
        if not self._request_boundary_allowed():
            self._reply_error(HTTPStatus.FORBIDDEN, "request origin is not allowed")
            return
        try:
            query = parse_qs(parsed.query, keep_blank_values=True)
            unknown = set(query) - {"scope", "q"}
            if unknown:
                raise ValueError("unsupported memory query parameter")
            scope_values = query.get("scope", [""])
            q_values = query.get("q", [""])
            if len(scope_values) != 1 or len(q_values) != 1:
                raise ValueError("memory query parameters must be specified at most once")
            scope = scope_values[0].strip() or None
            search_query = q_values[0].strip()
            state = self.transport.memory_state()
            records = self.transport.list_memories(scope=scope, query=search_query)
            self._reply_json(
                HTTPStatus.OK,
                {
                    **state,
                    "scope": scope,
                    "query": search_query,
                    "memories": records.get("memories", []),
                },
            )
        except ValueError as exc:
            self._reply_error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self._reply_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        mapped = None
        if parsed.path == "/v1/memory/settings":
            mapped = "/v1/memory/state"
        elif parsed.path == "/v1/memory":
            mapped = "/v1/memories"
        elif parsed.path.startswith("/v1/memory/"):
            mapped = "/v1/memories/" + parsed.path.removeprefix("/v1/memory/")
        if mapped is None:
            super().do_POST()
            return
        self.path = mapped
        super().do_POST()

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/v1/memory/"):
            self.path = "/v1/memories/" + parsed.path.removeprefix("/v1/memory/")
        super().do_DELETE()


class NativeAgentThreadingHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], transport: AgentHttpTransport) -> None:
        host, _port = address
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("AgentService HTTP transport may only bind to loopback")
        self.address_family = socket.AF_INET6 if host == "::1" else socket.AF_INET
        self.transport = transport
        super().__init__(address, _NativeHandler)


def create_native_http_server(
    service: AgentServiceCore,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> NativeAgentThreadingHttpServer:
    return NativeAgentThreadingHttpServer((host, port), AgentHttpTransport(service))
