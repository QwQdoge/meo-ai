from __future__ import annotations

import json
import queue
import socket
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse

from meo.service.backend_adapter import BackendCallbacks
from meo.service.core import AgentServiceCore, RequestContext
from meo.service.request_state import RequestState


class RequestEventStream:
    """Thread-safe event queue for one AgentService request."""

    def __init__(self) -> None:
        self._events: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def emit(self, event_type: str, **payload: Any) -> None:
        self._events.put({"type": event_type, **payload})

    def emit_event(self, event: dict[str, Any]) -> None:
        self._events.put(dict(event))

    def close(self) -> None:
        self._events.put(None)

    def __iter__(self):
        while True:
            event = self._events.get()
            if event is None:
                return
            yield event


class AgentHttpTransport:
    """Semantic adapter from loopback HTTP/SSE to AgentServiceCore.

    HTTP is an implementation detail for Phase B. Frontends consume the
    AgentService request/decision/event schema rather than Newelle v2 commands.
    """

    def __init__(self, service: AgentServiceCore) -> None:
        if service.backend is None:
            raise ValueError("AgentService HTTP transport requires a backend")
        self.service = service
        self._streams: dict[str, RequestEventStream] = {}
        self._lock = threading.Lock()

    def list_conversations(self) -> list[dict]:
        return list(self.service.backend.list_conversations())

    def create_conversation(self) -> dict:
        conversation_id = self.service.backend.create_conversation()
        return {"conversation_id": conversation_id}

    def send_message(self, conversation_id: str, text: str) -> tuple[str, RequestEventStream]:
        stream = RequestEventStream()
        request_box: dict[str, str] = {}

        def request_id() -> str:
            return request_box["id"]

        def on_started(context: RequestContext) -> None:
            request_box["id"] = context.request_id
            with self._lock:
                self._streams[context.request_id] = stream
            stream.emit(
                "request.started",
                request_id=context.request_id,
                conversation_id=conversation_id,
                state=self.service.get_request(context.request_id).state.value,
            )

        callbacks = BackendCallbacks(
            on_text_delta=lambda delta: stream.emit(
                "message.delta",
                request_id=request_id(),
                conversation_id=conversation_id,
                delta=delta,
            ),
            on_tool_event=lambda event: stream.emit_event(event),
            on_done=lambda: self._finish_stream(stream, request_id()),
            on_error=lambda error: self._fail_stream(stream, request_id(), error),
        )
        context = self.service.send_message(conversation_id, text, callbacks, on_started=on_started)
        return context.request_id, stream

    def _finish_stream(self, stream: RequestEventStream, request_id: str) -> None:
        request = self.service.get_request(request_id)
        event_type = "request.cancelled" if request.state is RequestState.CANCELLED else "request.completed"
        stream.emit(event_type, request_id=request_id, state=request.state.value)
        stream.close()
        with self._lock:
            self._streams.pop(request_id, None)

    def _fail_stream(self, stream: RequestEventStream, request_id: str, error: str) -> None:
        stream.emit("request.failed", request_id=request_id, error=error)
        stream.close()
        with self._lock:
            self._streams.pop(request_id, None)

    def choose_tool_option(self, request_id: str, decision_id: str, option_index: int) -> dict:
        legacy_index = self.service.choose_tool_option(request_id, decision_id, option_index)
        return {
            "request_id": request_id,
            "accepted": True,
            "legacy_option_index": legacy_index,
            "state": self.service.get_request(request_id).state.value,
        }

    def cancel_request(self, request_id: str) -> dict:
        accepted = self.service.cancel_request(request_id)
        request = self.service.get_request(request_id)
        return {"request_id": request_id, "accepted": accepted, "state": request.state.value}

    def get_request(self, request_id: str) -> dict:
        request = self.service.get_request(request_id)
        context = self.service.get_context(request_id)
        return {
            "request_id": request_id,
            "conversation_id": context.conversation_id,
            "state": request.state.value,
            "terminal": request.terminal,
            "error": request.error,
        }


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "MeoAgentService/0"

    @property
    def transport(self) -> AgentHttpTransport:
        return self.server.transport  # type: ignore[attr-defined]

    def log_message(self, _format: str, *_args) -> None:
        return

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0 or length > 1024 * 1024:
            raise ValueError("JSON body is required and must be <= 1 MiB")
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid JSON body") from exc
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def _reply_json(self, status: int, value: Any) -> None:
        body = _json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _reply_error(self, status: int, message: str) -> None:
        self._reply_json(status, {"error": message})

    def _segments(self) -> list[str]:
        parsed = urlparse(self.path)
        if parsed.query or parsed.fragment:
            return []
        return [unquote(segment) for segment in parsed.path.split("/") if segment]

    def do_GET(self) -> None:
        segments = self._segments()
        try:
            if segments == ["v1", "conversations"]:
                self._reply_json(HTTPStatus.OK, {"conversations": self.transport.list_conversations()})
                return
            if len(segments) == 3 and segments[:2] == ["v1", "requests"]:
                self._reply_json(HTTPStatus.OK, self.transport.get_request(segments[2]))
                return
            self._reply_error(HTTPStatus.NOT_FOUND, "not found")
        except ValueError as exc:
            self._reply_error(HTTPStatus.NOT_FOUND, str(exc))
        except Exception as exc:
            self._reply_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:
        segments = self._segments()
        try:
            if segments == ["v1", "conversations"]:
                self._reply_json(HTTPStatus.CREATED, self.transport.create_conversation())
                return
            if len(segments) == 4 and segments[:2] == ["v1", "conversations"] and segments[3] == "messages":
                body = self._read_json()
                text = body.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("text is required")
                request_id, stream = self.transport.send_message(segments[2], text)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.send_header("X-Meo-Request-Id", request_id)
                self.end_headers()
                for event in stream:
                    self.wfile.write(b"data: " + _json_bytes(event) + b"\n\n")
                    self.wfile.flush()
                self.close_connection = True
                return
            if len(segments) == 4 and segments[:2] == ["v1", "requests"] and segments[3] == "cancel":
                self._reply_json(HTTPStatus.OK, self.transport.cancel_request(segments[2]))
                return
            if len(segments) == 5 and segments[:2] == ["v1", "requests"] and segments[3] == "decisions":
                body = self._read_json()
                option_index = body.get("option_index")
                if not isinstance(option_index, int) or isinstance(option_index, bool):
                    raise ValueError("option_index must be an integer")
                self._reply_json(
                    HTTPStatus.OK,
                    self.transport.choose_tool_option(segments[2], segments[4], option_index),
                )
                return
            self._reply_error(HTTPStatus.NOT_FOUND, "not found")
        except ValueError as exc:
            self._reply_error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self._reply_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))


class AgentThreadingHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], transport: AgentHttpTransport) -> None:
        host, _port = address
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("AgentService HTTP transport may only bind to loopback")
        self.address_family = socket.AF_INET6 if host == "::1" else socket.AF_INET
        self.transport = transport
        super().__init__(address, _Handler)


def create_http_server(service: AgentServiceCore, host: str = "127.0.0.1", port: int = 8765) -> AgentThreadingHttpServer:
    return AgentThreadingHttpServer((host, port), AgentHttpTransport(service))
