from __future__ import annotations

from datetime import datetime, timezone

from meo.service.memory import MemoryRecord


class LegacyMemoryBridge:
    """Expose Newelle long-term memory through Meo's typed memory contract.

    The selected Newelle memory provider may not offer an inspectable store. In
    that case the bridge reports an empty catalog instead of scraping UI state or
    inventing records. LongTermMemoryHandler exposes a real MemoryStore, which is
    managed directly through its public store methods.
    """

    def __init__(self, controller) -> None:
        self.controller = controller

    def _handler(self):
        handlers = getattr(self.controller, "handlers", None)
        return getattr(handlers, "memory", None) if handlers is not None else None

    def _store_and_scope(self):
        handler = self._handler()
        store = getattr(handler, "store", None)
        get_scope = getattr(handler, "get_scope", None)
        if store is None or not callable(get_scope):
            return None, None
        return store, str(get_scope())

    @staticmethod
    def _public_id(raw_id: str) -> str:
        return "memory:" + str(raw_id)

    @staticmethod
    def _raw_id(memory_id: str) -> str:
        if not isinstance(memory_id, str) or not memory_id.startswith("memory:"):
            raise ValueError("invalid memory_id")
        raw = memory_id.removeprefix("memory:")
        if not raw:
            raise ValueError("invalid memory_id")
        return raw

    @staticmethod
    def _timestamp(value) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "1970-01-01T00:00:00Z"
        return datetime.fromtimestamp(number, timezone.utc).isoformat().replace("+00:00", "Z")

    @classmethod
    def _convert(cls, record, *, backend_scope: str) -> MemoryRecord:
        archived = bool(getattr(record, "archived", False))
        source = str(getattr(record, "source", "newelle") or "newelle")
        return MemoryRecord(
            memory_id=cls._public_id(getattr(record, "id")),
            text=str(getattr(record, "text", "")),
            scope="account",
            source=f"newelle:{source};scope={backend_scope}",
            created_at=cls._timestamp(getattr(record, "created_at", 0)),
            updated_at=cls._timestamp(getattr(record, "updated_at", 0)),
            state="disabled" if archived else "active",
            pinned=bool(getattr(record, "pinned", False)),
            sync_state="local",
        )

    def supported(self) -> bool:
        store, scope = self._store_and_scope()
        return store is not None and bool(scope)

    def memory_enabled(self) -> bool:
        settings = getattr(self.controller, "settings", None)
        getter = getattr(settings, "get_boolean", None)
        return bool(getter("memory-on")) if callable(getter) else False

    def set_memory_enabled(self, enabled: bool) -> bool:
        settings = getattr(self.controller, "settings", None)
        setter = getattr(settings, "set_boolean", None)
        if not callable(setter):
            raise ValueError("memory setting is unavailable")
        setter("memory-on", bool(enabled))
        return self.memory_enabled()

    def list_memories(self, *, scope: str | None = None, query: str = "") -> list[MemoryRecord]:
        if scope not in {None, "", "account"}:
            return []
        store, backend_scope = self._store_and_scope()
        if store is None or not backend_scope:
            return []
        records = store.list_records(backend_scope, archived=None)
        wanted = query.casefold().strip() if isinstance(query, str) else ""
        result = []
        for record in records:
            text = str(getattr(record, "text", ""))
            if wanted and wanted not in text.casefold():
                continue
            result.append(self._convert(record, backend_scope=backend_scope))
        return result

    def update_memory(
        self,
        memory_id: str,
        *,
        text: str | None = None,
        pinned: bool | None = None,
    ) -> MemoryRecord:
        store, backend_scope = self._store_and_scope()
        if store is None or not backend_scope:
            raise ValueError("selected memory provider is not inspectable")
        raw_id = self._raw_id(memory_id)
        current = store.get(raw_id)
        if current is None or str(getattr(current, "scope", "")) != backend_scope:
            raise ValueError("unknown memory_id")
        if text is not None:
            if not isinstance(text, str) or not text.strip():
                raise ValueError("memory text is required")
            current = store.update_text(raw_id, text)
        if pinned is not None:
            store.set_pinned(raw_id, bool(pinned))
            current = store.get(raw_id)
        if current is None:
            raise ValueError("unknown memory_id")
        notify = getattr(self._handler(), "_notify", None)
        if callable(notify):
            notify()
        return self._convert(current, backend_scope=backend_scope)

    def delete_memory(self, memory_id: str) -> None:
        store, backend_scope = self._store_and_scope()
        if store is None or not backend_scope:
            raise ValueError("selected memory provider is not inspectable")
        raw_id = self._raw_id(memory_id)
        current = store.get(raw_id)
        if current is None or str(getattr(current, "scope", "")) != backend_scope:
            raise ValueError("unknown memory_id")
        store.delete(raw_id)
        notify = getattr(self._handler(), "_notify", None)
        if callable(notify):
            notify()
