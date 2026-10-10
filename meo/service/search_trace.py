from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol, runtime_checkable


SEARCH_KINDS = {"web", "workspace", "local", "mcp", "retrieval"}


def _text(value: str, field: str, *, limit: int = 4096, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    if required and not value.strip():
        raise ValueError(f"{field} is required")
    if len(value) > limit:
        raise ValueError(f"{field} is too long")
    return value


@dataclass(frozen=True)
class SearchSource:
    source_id: str
    title: str
    uri: str = ""
    provider: str = ""
    snippet: str = ""

    def __post_init__(self) -> None:
        _text(self.source_id, "source_id", limit=256, required=True)
        _text(self.title, "title", limit=1024, required=True)
        _text(self.uri, "uri", limit=8192)
        _text(self.provider, "provider", limit=256)
        _text(self.snippet, "snippet", limit=8192)

    def public_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "uri": self.uri,
            "provider": self.provider,
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class SearchTrace:
    trace_id: str
    kind: str
    queries: tuple[str, ...] = field(default_factory=tuple)
    provider: str = ""
    duration_ms: float | None = None
    result_count: int | None = None
    sources: tuple[SearchSource, ...] = field(default_factory=tuple)
    filters: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.trace_id, "trace_id", limit=256, required=True)
        if self.kind not in SEARCH_KINDS:
            raise ValueError("unsupported search kind")
        if len(self.queries) > 64 or len(self.sources) > 256 or len(self.filters) > 64:
            raise ValueError("search trace exceeds bounded collection size")
        for query in self.queries:
            _text(query, "query", limit=8192, required=True)
        _text(self.provider, "provider", limit=256)
        if self.duration_ms is not None and (isinstance(self.duration_ms, bool) or self.duration_ms < 0):
            raise ValueError("duration_ms must be non-negative")
        if self.result_count is not None and (
            isinstance(self.result_count, bool) or not isinstance(self.result_count, int) or self.result_count < 0
        ):
            raise ValueError("result_count must be a non-negative integer")
        for key, value in self.filters.items():
            _text(str(key), "filter key", limit=128, required=True)
            _text(str(value), "filter value", limit=1024)

    def public_dict(self) -> dict:
        result = {
            "trace_id": self.trace_id,
            "kind": self.kind,
            "queries": list(self.queries),
            "provider": self.provider,
            "sources": [item.public_dict() for item in self.sources],
            "filters": dict(self.filters),
        }
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        if self.result_count is not None:
            result["result_count"] = self.result_count
        return result


@runtime_checkable
class SearchTraceBackend(Protocol):
    """Optional source for durable/inspectable research traces."""

    def list_search_traces(self, conversation_id: str) -> Iterable[SearchTrace]: ...
