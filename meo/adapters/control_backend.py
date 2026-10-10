from __future__ import annotations

import time
from typing import Any

from meo.adapters.legacy_controls import LegacyAiControls
from meo.adapters.legacy_memory import LegacyMemoryBridge
from meo.service.backend_adapter import BackendCallbacks
from meo.service.response_meta import configured_context_from_usage
from meo.service.search_trace import SearchSource, SearchTrace


class ControlledLegacyBackend:
    """Add Meo product surfaces without widening the inherited chat adapter.

    Unknown attributes deliberately delegate to the wrapped backend so current
    AgentBackendAdapter/resource/presentation behavior remains unchanged. The
    wrappers keep Newelle-specific settings and memory/search storage behind
    typed Meo contracts that can be replaced independently later.
    """

    def __init__(self, backend, controller) -> None:
        self._backend = backend
        self._controller = controller
        self._controls = LegacyAiControls(controller)
        self._memory = LegacyMemoryBridge(controller)

    def __getattr__(self, name: str):
        return getattr(self._backend, name)

    def _setting_int(self, key: str) -> int | None:
        settings = getattr(self._controller, "settings", None)
        getter = getattr(settings, "get_int", None)
        if not callable(getter):
            return None
        try:
            value = getter(key)
        except Exception:
            return None
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

    def _effective_control_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        try:
            controls = self._controls.list_controls()
        except Exception:
            return values
        for control in controls:
            control_id = getattr(control, "control_id", "")
            if isinstance(control_id, str) and control_id:
                values[control_id] = getattr(control, "value", None)
        return values

    def _legacy_chat_id(self, conversation_id: str) -> int | None:
        try:
            conversations = self._backend.list_conversations()
        except Exception:
            return None
        for item in conversations:
            if not isinstance(item, dict) or item.get("id") != conversation_id:
                continue
            chat_id = item.get("legacy_chat_id")
            if isinstance(chat_id, int) and not isinstance(chat_id, bool):
                return chat_id
        return None

    def _websearch_integration(self):
        loader = getattr(self._controller, "integrationsloader", None)
        mapping = getattr(loader, "extensionsmap", None)
        if isinstance(mapping, dict):
            integration = mapping.get("websearch")
            if integration is not None:
                return integration
        extensions = getattr(loader, "extensions", ())
        for integration in extensions or ():
            if getattr(integration, "id", "") == "websearch":
                return integration
        return None

    def _consume_search_metadata(self, conversation_id: str, started_at: float) -> tuple[dict | None, list[dict]]:
        integration = self._websearch_integration()
        consumer = getattr(integration, "consume_meo_search_traces", None)
        chat_id = self._legacy_chat_id(conversation_id)
        if not callable(consumer) or chat_id is None:
            return None, []
        try:
            raw_traces = consumer(chat_id, started_at)
        except Exception:
            return None, []

        traces: list[dict] = []
        citations: list[dict] = []
        queries: list[str] = []
        result_count = 0
        for raw in raw_traces[:32]:
            if not isinstance(raw, dict):
                continue
            raw_sources = raw.get("sources")
            sources: list[SearchSource] = []
            if isinstance(raw_sources, list):
                for index, item in enumerate(raw_sources[:256]):
                    if not isinstance(item, dict):
                        continue
                    uri = str(item.get("uri", ""))[:8192]
                    title = str(item.get("title", "") or uri or f"Source {index + 1}")[:1024]
                    provider = str(raw.get("provider", ""))[:256]
                    try:
                        source = SearchSource(
                            source_id=f"{raw.get('trace_id', 'search')}:{index + 1}",
                            title=title,
                            uri=uri,
                            provider=provider,
                        )
                    except ValueError:
                        continue
                    sources.append(source)
                    citations.append(source.public_dict())

            query = str(raw.get("query", "")).strip()[:8192]
            if not query:
                continue
            filters = raw.get("filters") if isinstance(raw.get("filters"), dict) else {}
            safe_filters = {str(key)[:128]: str(value)[:1024] for key, value in list(filters.items())[:64]}
            error = raw.get("error")
            if isinstance(error, str) and error:
                safe_filters["error"] = error[:1024]
            duration = raw.get("duration_ms")
            duration_ms = duration if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration >= 0 else None
            count = raw.get("result_count")
            count = count if isinstance(count, int) and not isinstance(count, bool) and count >= 0 else len(sources)
            try:
                trace = SearchTrace(
                    trace_id=str(raw.get("trace_id") or f"search:{len(traces) + 1}")[:256],
                    kind="web",
                    queries=(query,),
                    provider=str(raw.get("provider", ""))[:256],
                    duration_ms=duration_ms,
                    result_count=count,
                    sources=tuple(sources),
                    filters=safe_filters,
                )
            except ValueError:
                continue
            traces.append(trace.public_dict())
            queries.append(query)
            result_count += count

        if not traces:
            return None, []
        return {
            "used": True,
            "queries": queries,
            "result_count": result_count,
            "traces": traces,
        }, citations

    def _enrich_response_event(self, event: dict, *, conversation_id: str = "", started_at: float = 0.0) -> dict:
        if event.get("type") != "response_meta":
            return event
        enriched = dict(event)
        usage = enriched.get("usage")
        enriched["context"] = configured_context_from_usage(
            usage if isinstance(usage, dict) else {},
            configured_budget=self._setting_int("context-max"),
            suggested_target=self._setting_int("context-suggested"),
        )
        enriched["controls"] = self._effective_control_values()

        search, citations = self._consume_search_metadata(conversation_id, started_at)
        if search is not None:
            activity = dict(enriched.get("activity")) if isinstance(enriched.get("activity"), dict) else {}
            activity["search"] = search
            activity["web"] = {"used": True, "result_count": search["result_count"]}
            enriched["activity"] = activity
            enriched["citations"] = citations
        return enriched

    def _wrap_callbacks(
        self,
        callbacks: BackendCallbacks,
        *,
        conversation_id: str,
        started_at: float,
    ) -> BackendCallbacks:
        return BackendCallbacks(
            on_text_delta=callbacks.on_text_delta,
            on_tool_event=lambda event: callbacks.on_tool_event(
                self._enrich_response_event(
                    event,
                    conversation_id=conversation_id,
                    started_at=started_at,
                )
            ),
            on_done=callbacks.on_done,
            on_error=callbacks.on_error,
        )

    def send_message(self, conversation_id: str, text: str, callbacks: BackendCallbacks):
        started_at = time.monotonic()
        return self._backend.send_message(
            conversation_id,
            text,
            self._wrap_callbacks(
                callbacks,
                conversation_id=conversation_id,
                started_at=started_at,
            ),
        )

    def send_message_with_resources(self, conversation_id: str, text: str, resources, callbacks: BackendCallbacks):
        method = getattr(self._backend, "send_message_with_resources", None)
        if not callable(method):
            raise ValueError("selected backend does not support resource inputs")
        started_at = time.monotonic()
        return method(
            conversation_id,
            text,
            resources,
            self._wrap_callbacks(
                callbacks,
                conversation_id=conversation_id,
                started_at=started_at,
            ),
        )

    def list_controls(self):
        return self._controls.list_controls()

    def set_control(self, control_id: str, value: Any):
        return self._controls.set_control(control_id, value)

    def memory_supported(self) -> bool:
        return self._memory.supported()

    def memory_enabled(self) -> bool:
        return self._memory.memory_enabled()

    def set_memory_enabled(self, enabled: bool) -> bool:
        return self._memory.set_memory_enabled(enabled)

    def list_memories(self, *, scope: str | None = None, query: str = ""):
        return self._memory.list_memories(scope=scope, query=query)

    def create_memory(self, text: str, *, pinned: bool = False):
        return self._memory.create_memory(text, pinned=pinned)

    def update_memory(self, memory_id: str, *, text: str | None = None, pinned: bool | None = None):
        return self._memory.update_memory(memory_id, text=text, pinned=pinned)

    def delete_memory(self, memory_id: str) -> None:
        self._memory.delete_memory(memory_id)
