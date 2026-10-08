from __future__ import annotations

from collections import OrderedDict
import json
import socket
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator
from urllib.parse import parse_qs, unquote, urlparse

from meo.runtime.event_journal import JournalGapError, RequestEventJournal
from meo.service.backend_adapter import BackendCallbacks
from meo.service.core import AgentServiceCore, RequestContext
from meo.service.request_state import RequestState


class AgentHttpTransport:
    """Semantic adapter from loopback HTTP/SSE to AgentServiceCore."""

    def __init__(self, service: AgentServiceCore, *, retained_terminal_journals: int = 32) -> None:
        if service.backend is None:
            raise ValueError("AgentService HTTP transport requires a backend")
        if retained_terminal_journals < 1:
            raise ValueError("retained_terminal_journals must be positive")
        self.service = service
        self._journals: OrderedDict[str, RequestEventJournal] = OrderedDict()
        self._retained_terminal_journals = retained_terminal_journals
        self._lock = threading.Lock()

    def list_conversations(self) -> list[dict]:
        return self.service.list_conversations()

    def create_conversation(self) -> dict:
        return {"conversation_id": self.service.create_conversation()}

    def list_models(self) -> list[dict]:
        return self.service.list_models()

    def set_model(self, conversation_id: str, model_id: str) -> dict:
        self.service.set_model(conversation_id, model_id)
        return {"conversation_id": conversation_id, "model_id": model_id, "accepted": True}

    def list_skills(self) -> list[dict]:
        return self.service.list_skills()

    def set_skill_enabled(self, skill_id: str, enabled: bool) -> dict:
        self.service.set_skill_enabled(skill_id, enabled)
        return {"skill_id": skill_id, "enabled": enabled, "accepted": True}

    def list_mcp_servers(self) -> list[dict]:
        return self.service.list_mcp_servers()

    def send_message(self, conversation_id: str, text: str) -> tuple[str, RequestEventJournal]:
        journal = RequestEventJournal()
        request_box: dict[str, str] = {}

        def request_id() -> str:
            return request_box["id"]

        def on_started(context: RequestContext) -> None:
            request_box["id"] = context.request_id
            with self._lock:
                self._journals[context.request_id] = journal
            journal.append({
                "type": "request.started",
                "request_id": context.request_id,
                "conversation_id": conversation_id,
                "state": self.service.get_request(context.request_id).state.value,
            })

        callbacks = BackendCallbacks(
            on_text_delta=lambda delta: journal.append({
                "type": "message.delta",
                "request_id": request_id(),
                "conversation_id": conversation_id,
                "delta": delta,
            }),
            on_tool_event=lambda event: journal.append(event),
            on_done=lambda: self._finish_journal(journal, request_id()),
            on_error=lambda error: self._fail_journal(journal, request_id(), error),
        )
        context = self.service.send_message(conversation_id, text, callbacks, on_started=on_started)
        return context.request_id, journal

    def _finish_journal(self, journal: RequestEventJournal, request_id: str) -> None:
        request = self.service.get_request(request_id)
        event_type = "request.cancelled" if request.state is RequestState.CANCELLED else "request.completed"
        journal.append({"type": event_type, "request_id": request_id, "state": request.state.value})
        journal.close()
        self._prune_terminal_journals()

    def _fail_journal(self, journal: RequestEventJournal, request_id: str, error: str) -> None:
        journal.append({"type": "request.failed", "request_id": request_id, "error": error})
        journal.close()
        self._prune_terminal_journals()

    def _prune_terminal_journals(self) -> None:
        with self._lock:
            closed_ids = [
                request_id
                for request_id, journal in self._journals.items()
                if journal.snapshot().closed
            ]
            for request_id in closed_ids[:-self._retained_terminal_journals]:
                self._journals.pop(request_id, None)

    def get_event_journal(self, request_id: str) -> RequestEventJournal:
        # Validate service request identity first so a pruned/unknown event
        # journal never becomes an alternate request-existence oracle.
        self.service.get_request(request_id)
        with self._lock:
            journal = self._journals.get(request_id)
        if journal is None:
            raise ValueError("request event journal is no longer retained")
        return journal

    def stream_events(self, request_id: str, after_seq: int = 0) -> Iterator[dict[str, Any]]:
        journal = self.get_event_journal(request_id)
        snapshot = journal.snapshot()
        if after_seq and after_seq < snapshot.oldest_seq - 1:
            raise JournalGapError(
                f"event cursor {after_seq} predates retained journal starting at {snapshot.oldest_seq}"
            )
        return journal.subscribe(after_seq)

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
        result = {
            "request_id": request_id,
            "conversation_id": context.conversation_id,
            "state": request.state.value,
            "terminal": request.terminal,
            "error": request.error,
        }
        try:
            snapshot = self.get_event_journal(request_id).snapshot()
        except ValueError:
            result["event_journal"] = None
        else:
            result["event_journal"] = {
                "oldest_seq": snapshot.oldest_seq,
                "latest_seq": snapshot.latest_seq,
                "closed": snapshot.closed,
            }
        return result


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _loopback_host_header(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse("//" + value)
    except ValueError:
        return False
    return parsed.hostname in {"127.0.0.1", "localhost", "::1"}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "MeoAgentService/0"

    @property
    def transport(self) -> AgentHttpTransport:
        return self.server.transport  # type: ignore[attr-defined]

    def log_message(self, _format: str, *_args) -> None:
        return

    def _request_boundary_allowed(self) -> bool:
        return _loopback_host_header(self.headers.get("Host")) and not self.headers.get("Origin")

    def _post_content_type_allowed(self) -> bool:
        content_type = self.headers.get("Content-Type", "")
        return content_type.split(";", 1)[0].strip().lower() == "application/json"

    def _read_json(self, *, allow_empty: bool = False) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length == 0 and allow_empty:
            return {}
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

    def _route(self) -> tuple[list[str], dict[str, list[str]]]:
        parsed = urlparse(self.path)
        if parsed.fragment:
            return [], {}
        segments = [unquote(segment) for segment in parsed.path.split("/") if segment]
        return segments, parse_qs(parsed.query, keep_blank_values=True)

    def _write_event_stream(self, events: Iterator[dict[str, Any]], request_id: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.send_header("X-Meo-Request-Id", request_id)
        self.end_headers()
        try:
            for event in events:
                self.wfile.write(b"data: " + _json_bytes(event) + b"\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # Transport disconnect is not cancellation.
            pass
        self.close_connection = True

    def do_OPTIONS(self) -> None:
        self._reply_error(HTTPStatus.FORBIDDEN, "browser cross-origin access is not allowed")

    def do_GET(self) -> None:
        if not self._request_boundary_allowed():
            self._reply_error(HTTPStatus.FORBIDDEN, "request origin is not allowed")
            return
        segments, query = self._route()
        try:
            if segments == ["v1", "conversations"] and not query:
                self._reply_json(HTTPStatus.OK, {"conversations": self.transport.list_conversations()})
                return
            if segments == ["v1", "models"] and not query:
                self._reply_json(HTTPStatus.OK, {"models": self.transport.list_models()})
                return
            if segments == ["v1", "skills"] and not query:
                self._reply_json(HTTPStatus.OK, {"skills": self.transport.list_skills()})
                return
            if segments == ["v1", "mcp-servers"] and not query:
                self._reply_json(HTTPStatus.OK, {"mcp_servers": self.transport.list_mcp_servers()})
                return
            if len(segments) == 3 and segments[:2] == ["v1", "requests"] and not query:
                self._reply_json(HTTPStatus.OK, self.transport.get_request(segments[2]))
                return
            if len(segments) == 4 and segments[:2] == ["v1", "requests"] and segments[3] == "events":
                unknown = set(query) - {"after"}
                if unknown:
                    raise ValueError("unsupported event-stream query parameter")
                values = query.get("after", ["0"])
                if len(values) != 1:
                    raise ValueError("after must be specified once")
                try:
                    after_seq = int(values[0])
                except ValueError as exc:
                    raise ValueError("after must be a non-negative integer") from exc
                events = self.transport.stream_events(segments[2], after_seq)
                self._write_event_stream(events, segments[2])
                return
            self._reply_error(HTTPStatus.NOT_FOUND, "not found")
        except JournalGapError as exc:
            self._reply_error(HTTPStatus.CONFLICT, str(exc))
        except ValueError as exc:
            self._reply_error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self._reply_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:
        if not self._request_boundary_allowed():
            self._reply_error(HTTPStatus.FORBIDDEN, "request origin is not allowed")
            return
        if not self._post_content_type_allowed():
            self._reply_error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "POST requires application/json")
            return
        segments, query = self._route()
        if query:
            self._reply_error(HTTPStatus.BAD_REQUEST, "POST query parameters are not supported")
            return
        try:
            if segments == ["v1", "conversations"]:
                self._read_json(allow_empty=True)
                self._reply_json(HTTPStatus.CREATED, self.transport.create_conversation())
                return
            if len(segments) == 4 and segments[:2] == ["v1", "conversations"] and segments[3] == "model":
                body = self._read_json()
                model_id = body.get("model_id")
                if not isinstance(model_id, str) or not model_id.strip():
                    raise ValueError("model_id is required")
                self._reply_json(HTTPStatus.OK, self.transport.set_model(segments[2], model_id))
                return
            if len(segments) == 3 and segments[:2] == ["v1", "skills"]:
                body = self._read_json()
                enabled = body.get("enabled")
                if not isinstance(enabled, bool):
                    raise ValueError("enabled must be a boolean")
                self._reply_json(HTTPStatus.OK, self.transport.set_skill_enabled(segments[2], enabled))
                return
            if len(segments) == 4 and segments[:2] == ["v1", "conversations"] and segments[3] == "messages":
                body = self._read_json()
                text = body.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("text is required")
                request_id, journal = self.transport.send_message(segments[2], text)
                self._write_event_stream(journal.subscribe(0), request_id)
                return
            if len(segments) == 4 and segments[:2] == ["v1", "requests"] and segments[3] == "cancel":
                self._read_json(allow_empty=True)
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
