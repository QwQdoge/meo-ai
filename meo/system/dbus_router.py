from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
import threading
from typing import Any, Awaitable, Callable, Mapping


ROUTER_BUS_NAME = "org.meo.AIRouter1"
ROUTER_OBJECT_PATH = "/org/meo/AIRouter1"
ROUTER_INTERFACE = "org.meo.AIRouter1"


class RouterUnavailable(RuntimeError):
    """Raised when the session-bus Router cannot be reached safely."""


class DbusNextRouterClient:
    """Persistent org.meo.AIRouter1 client using one session-bus identity.

    Router requests are caller-bound. SubmitRequest, GetRequest and
    DecideRequest therefore must share the same D-Bus connection; spawning a
    command per call would produce different unique bus names and break the
    authorization contract.

    dbus-next is imported lazily so protocol/unit tests do not need it. MeoArch
    packaging that enables this adapter must install python-dbus-next.
    """

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        _connect: Callable[[], Awaitable[tuple[object, object]]] | None = None,
        _variant_factory: Callable[[str, Any], object] | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._timeout = timeout
        self._connect_override = _connect
        self._variant_factory_override = _variant_factory
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="meo-router-dbus", daemon=True)
        self._bus: object | None = None
        self._interface: object | None = None
        self._connect_task: asyncio.Task | None = None
        self._closed = False
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
        pending = asyncio.all_tasks(self._loop)
        for task in pending:
            task.cancel()
        if pending:
            self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self._loop.close()

    async def _connect_default(self) -> tuple[object, object]:
        try:
            from dbus_next.aio import MessageBus
            from dbus_next.constants import BusType
        except ImportError as exc:
            raise RouterUnavailable(
                "python-dbus-next is required for the Meo System Router client"
            ) from exc

        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        introspection = await bus.introspect(ROUTER_BUS_NAME, ROUTER_OBJECT_PATH)
        proxy = bus.get_proxy_object(ROUTER_BUS_NAME, ROUTER_OBJECT_PATH, introspection)
        interface = proxy.get_interface(ROUTER_INTERFACE)
        return bus, interface

    async def _get_interface(self):
        if self._interface is not None:
            return self._interface
        if self._connect_task is None:
            factory = self._connect_override or self._connect_default
            self._connect_task = asyncio.create_task(factory())
        try:
            bus, interface = await self._connect_task
        except Exception:
            self._connect_task = None
            raise
        self._bus = bus
        self._interface = interface
        return interface

    def _run(self, coroutine):
        if self._closed:
            close = getattr(coroutine, "close", None)
            if callable(close):
                close()
            raise RouterUnavailable("Router client is closed")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout=self._timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise RouterUnavailable("System AI Router D-Bus call timed out") from exc
        except RouterUnavailable:
            raise
        except Exception as exc:
            raise RouterUnavailable(f"System AI Router D-Bus call failed: {exc}") from exc

    def _variant_factory(self):
        if self._variant_factory_override is not None:
            return self._variant_factory_override
        try:
            from dbus_next import Variant
        except ImportError as exc:
            raise RouterUnavailable(
                "python-dbus-next is required for the Meo System Router client"
            ) from exc
        return Variant

    def _variant(self, value: Any):
        factory = self._variant_factory()
        if isinstance(value, bool):
            return factory("b", value)
        if isinstance(value, int):
            if value < -(2**31) or value > 2**31 - 1:
                raise ValueError("integer argument does not fit D-Bus int32")
            return factory("i", value)
        if isinstance(value, float):
            return factory("d", value)
        if isinstance(value, str):
            return factory("s", value)
        if isinstance(value, dict):
            return factory("a{sv}", self._variant_map(value))
        if isinstance(value, list):
            if not value:
                raise ValueError("empty list argument has no inferable D-Bus element type")
            if all(isinstance(item, bool) for item in value):
                return factory("ab", list(value))
            if all(isinstance(item, int) and not isinstance(item, bool) for item in value):
                if any(item < -(2**31) or item > 2**31 - 1 for item in value):
                    raise ValueError("integer list argument does not fit D-Bus int32")
                return factory("ai", list(value))
            if all(isinstance(item, float) for item in value):
                return factory("ad", list(value))
            if all(isinstance(item, str) for item in value):
                return factory("as", list(value))
            raise ValueError("list argument must contain one supported scalar D-Bus type")
        raise ValueError(f"unsupported D-Bus argument type: {type(value).__name__}")

    def _variant_map(self, values: Mapping[str, Any]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values.items():
            if not isinstance(key, str) or not key:
                raise ValueError("D-Bus argument keys must be non-empty strings")
            result[key] = self._variant(value)
        return result

    @staticmethod
    def _unwrap(value: Any) -> Any:
        # dbus-next Variant intentionally has a small public surface: signature
        # and value. Avoid importing it here so tests can use lightweight fakes.
        if hasattr(value, "signature") and hasattr(value, "value"):
            return DbusNextRouterClient._unwrap(value.value)
        if isinstance(value, dict):
            return {str(key): DbusNextRouterClient._unwrap(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [DbusNextRouterClient._unwrap(item) for item in value]
        return value

    async def _list_capabilities(self):
        interface = await self._get_interface()
        return self._unwrap(await interface.call_list_capabilities())

    def list_capabilities(self) -> list[Mapping[str, Any]]:
        value = self._run(self._list_capabilities())
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise RouterUnavailable("Router returned an invalid capability list")
        return value

    async def _submit_request(self, capability_id: str, arguments: Mapping[str, Any]):
        interface = await self._get_interface()
        return self._unwrap(
            await interface.call_submit_request(capability_id, self._variant_map(arguments))
        )

    def submit_request(self, capability_id: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        value = self._run(self._submit_request(capability_id, arguments))
        if not isinstance(value, dict):
            raise RouterUnavailable("Router returned an invalid request view")
        return value

    async def _get_request(self, request_id: str):
        interface = await self._get_interface()
        return self._unwrap(await interface.call_get_request(request_id))

    def get_request(self, request_id: str) -> Mapping[str, Any]:
        value = self._run(self._get_request(request_id))
        if not isinstance(value, dict):
            raise RouterUnavailable("Router returned an invalid request view")
        return value

    async def _decide_request(self, request_id: str, fingerprint: str, approve: bool):
        interface = await self._get_interface()
        return self._unwrap(await interface.call_decide_request(request_id, fingerprint, approve))

    def decide_request(self, request_id: str, fingerprint: str, approve: bool) -> Mapping[str, Any]:
        value = self._run(self._decide_request(request_id, fingerprint, approve))
        if not isinstance(value, dict):
            raise RouterUnavailable("Router returned an invalid request view")
        return value

    async def _disconnect(self) -> None:
        if self._bus is not None:
            disconnect = getattr(self._bus, "disconnect", None)
            if callable(disconnect):
                disconnect()
        self._bus = None
        self._interface = None

    def close(self) -> None:
        if self._closed:
            return
        try:
            future = asyncio.run_coroutine_threadsafe(self._disconnect(), self._loop)
            future.result(timeout=min(self._timeout, 2.0))
        except Exception:
            pass
        self._closed = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=2.0)

    def __enter__(self) -> "DbusNextRouterClient":
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()

    def __del__(self) -> None:
        # Best-effort only; callers should use close() or a context manager.
        if not getattr(self, "_closed", True):
            try:
                self.close()
            except Exception:
                pass
