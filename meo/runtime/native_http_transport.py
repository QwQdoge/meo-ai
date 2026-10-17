from __future__ import annotations

import socket
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from meo.runtime.http_transport import AgentHttpTransport, _Handler
from meo.service.core import AgentServiceCore


_CONVERSATION_METADATA_FIELDS = (
    "title",
    "summary",
    "title_is_default",
    "title_is_automatic",
)


class NativeAgentHttpTransport(AgentHttpTransport):
    """Native presentation additions layered over the canonical transport."""

    def list_messages(self, conversation_id: str) -> dict:
        payload = super().list_messages(conversation_id)
        metadata: dict = {"conversation_id": conversation_id}
        try:
            conversations = self.service.list_conversations()
        except Exception:
            conversations = []

        for item in conversations:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id", item.get("conversation_id"))
            if item_id != conversation_id:
                continue
            for key in _CONVERSATION_METADATA_FIELDS:
                value = item.get(key)
                if isinstance(value, str):
                    value = value.strip()
                    if value:
                        metadata[key] = value
                elif isinstance(value, bool):
                    metadata[key] = value
            break

        payload["conversation"] = metadata
        return payload

    def _conversation_management_method(self, name: str):
        backend = self.service.backend
        method = getattr(backend, name, None) if backend is not None else None
        if not callable(method):
            raise ValueError("selected backend does not support conversation management")
        return method

    def search_conversations(self, query: str) -> dict:
        query = " ".join(str(query or "").split()).strip()
        if not query:
            return {"query": "", "results": []}
        if len(query) > 240:
            raise ValueError("conversation search query is too long")
        method = self._conversation_management_method("search_conversations")
        raw_results = method(query)
        if not isinstance(raw_results, list):
            raw_results = []

        catalog = {
            item.get("id"): item
            for item in self.service.list_conversations()
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        results: list[dict] = []
        for value in raw_results[:100]:
            if not isinstance(value, dict):
                continue
            conversation_id = value.get("id")
            if not isinstance(conversation_id, str) or conversation_id not in catalog:
                continue
            output = {"id": conversation_id}
            metadata = catalog[conversation_id]
            for key in ("title", "summary", "message_count"):
                if key in metadata:
                    output[key] = metadata[key]
            excerpt = value.get("excerpt")
            if isinstance(excerpt, str) and excerpt.strip():
                output["excerpt"] = excerpt.strip()[:1200]
            results.append(output)
        return {"query": query, "results": results}

    def _conversation_has_active_request(self, conversation_id: str) -> bool:
        contexts = tuple(getattr(self.service, "_contexts", {}).items())
        for request_id, context in contexts:
            if getattr(context, "conversation_id", None) != conversation_id:
                continue
            try:
                if not self.service.get_request(request_id).terminal:
                    return True
            except ValueError:
                continue
        return False

    def rename_conversation(self, conversation_id: str, title: str) -> dict:
        backend = self.service.backend
        if backend is None or not backend.conversation_exists(conversation_id):
            raise ValueError("unknown conversation_id")
        title = " ".join(title.split()).strip()
        if not title:
            raise ValueError("conversation title is required")
        if len(title) > 240:
            raise ValueError("conversation title is too long")
        self._conversation_management_method("rename_conversation")(conversation_id, title)
        return {
            "accepted": True,
            "conversation_id": conversation_id,
            "title": title,
        }

    def delete_conversation(self, conversation_id: str) -> dict:
        backend = self.service.backend
        if backend is None or not backend.conversation_exists(conversation_id):
            raise ValueError("unknown conversation_id")
        if self._conversation_has_active_request(conversation_id):
            raise ValueError("conversation has an active request")

        store = self.service.resource_store
        resources = list(store.list_resources(conversation_id)) if store is not None else []
        self._conversation_management_method("delete_conversation")(conversation_id)
        if store is not None:
            for record in resources:
                try:
                    store.delete(conversation_id, record.resource_id)
                except ValueError:
                    pass
        return {
            "accepted": True,
            "conversation_id": conversation_id,
            "deleted": True,
        }


class _NativeHandler(_Handler):
    """Native-client compatibility routes kept at the loopback transport edge."""

    @property
    def transport(self) -> NativeAgentHttpTransport:
        return self.server.transport  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/v1/conversations/search":
            if not self._request_boundary_allowed():
                self._reply_error(HTTPStatus.FORBIDDEN, "request origin is not allowed")
                return
            try:
                query = parse_qs(parsed.query, keep_blank_values=True)
                if set(query) - {"q"}:
                    raise ValueError("unsupported conversation search query parameter")
                q_values = query.get("q", [""])
                if len(q_values) != 1:
                    raise ValueError("conversation search query must be specified at most once")
                payload = self.transport.search_conversations(q_values[0])
                self._reply_json(HTTPStatus.OK, payload)
            except ValueError as exc:
                self._reply_error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:
                self._reply_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return

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
        segments, query = self._route()
        if len(segments) == 4 and segments[:2] == ["v1", "conversations"] and segments[3] == "title":
            if not self._request_boundary_allowed():
                self._reply_error(HTTPStatus.FORBIDDEN, "request origin is not allowed")
                return
            if not self._post_content_type_allowed():
                self._reply_error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "POST requires application/json")
                return
            if query:
                self._reply_error(HTTPStatus.BAD_REQUEST, "POST query parameters are not supported")
                return
            try:
                body = self._read_json()
                title = body.get("title")
                if not isinstance(title, str):
                    raise ValueError("conversation title is required")
                payload = self.transport.rename_conversation(segments[2], title)
                self._reply_json(HTTPStatus.OK, payload)
            except ValueError as exc:
                status = HTTPStatus.NOT_FOUND if str(exc) == "unknown conversation_id" else HTTPStatus.BAD_REQUEST
                self._reply_error(status, str(exc))
            except Exception as exc:
                self._reply_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return

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
        segments, query = self._route()
        if len(segments) == 3 and segments[:2] == ["v1", "conversations"]:
            if not self._request_boundary_allowed():
                self._reply_error(HTTPStatus.FORBIDDEN, "request origin is not allowed")
                return
            if query:
                self._reply_error(HTTPStatus.BAD_REQUEST, "DELETE query parameters are not supported")
                return
            try:
                payload = self.transport.delete_conversation(segments[2])
                self._reply_json(HTTPStatus.OK, payload)
            except ValueError as exc:
                if str(exc) == "unknown conversation_id":
                    status = HTTPStatus.NOT_FOUND
                elif str(exc) == "conversation has an active request":
                    status = HTTPStatus.CONFLICT
                else:
                    status = HTTPStatus.BAD_REQUEST
                self._reply_error(status, str(exc))
            except Exception as exc:
                self._reply_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return

        parsed = urlparse(self.path)
        if parsed.path.startswith("/v1/memory/"):
            self.path = "/v1/memories/" + parsed.path.removeprefix("/v1/memory/")
        super().do_DELETE()


class NativeAgentThreadingHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], transport: NativeAgentHttpTransport) -> None:
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
    return NativeAgentThreadingHttpServer((host, port), NativeAgentHttpTransport(service))