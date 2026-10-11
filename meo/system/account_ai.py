from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
import threading
from typing import Any, Awaitable, Callable, Mapping


ACCOUNT_BUS_NAME = "org.meo.Accounts1"
ACCOUNT_OBJECT_PATH = "/org/meo/Accounts1"
ACCOUNT_INTERFACE = "org.meo.Accounts1"
MEO_AI_CLIENT_ID = "org.meo.MeoAI"
_TERMINAL_STATES = frozenset({"completed", "failed", "denied", "expired"})


class AccountAiUnavailable(RuntimeError):
    """Raised when the Meo Account AI broker cannot complete a safe request."""


@dataclass(frozen=True)
class PreparedAccountInference:
    """One Account-bound inference approval prepared from immutable arguments."""

    arguments: Mapping[str, Any]
    consent: Mapping[str, Any]
    request_id: str


class DbusNextAccountAiClient:
    """Persistent Meo Account local-AI client for AgentService.

    The broker authorizes the calling executable and keeps provider credentials
    in KWallet. This class never accepts, returns, or stores an API key.  A
    persistent session-bus identity is kept for the full client lifetime so the
    broker can continue to bind every request to the same trusted process.
    """

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        operation_timeout: float = 60.0,
        poll_interval: float = 0.05,
        _connect: Callable[[], Awaitable[tuple[object, object]]] | None = None,
        _variant_factory: Callable[[str, Any], object] | None = None,
    ) -> None:
        if timeout <= 0 or operation_timeout <= 0 or poll_interval <= 0:
            raise ValueError("Account AI timeouts and poll interval must be positive")
        self._timeout = timeout
        self._operation_timeout = operation_timeout
        self._poll_interval = poll_interval
        self._connect_override = _connect
        self._variant_factory_override = _variant_factory
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, name="meo-account-ai-dbus", daemon=True
        )
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
            raise AccountAiUnavailable(
                "python-dbus-next is required for the Meo Account AI broker client"
            ) from exc

        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        introspection = await bus.introspect(ACCOUNT_BUS_NAME, ACCOUNT_OBJECT_PATH)
        proxy = bus.get_proxy_object(ACCOUNT_BUS_NAME, ACCOUNT_OBJECT_PATH, introspection)
        interface = proxy.get_interface(ACCOUNT_INTERFACE)
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

    def _run(self, coroutine, *, timeout: float | None = None):
        if self._closed:
            close = getattr(coroutine, "close", None)
            if callable(close):
                close()
            raise AccountAiUnavailable("Meo Account AI broker client is closed")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout=timeout or self._timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise AccountAiUnavailable("Meo Account AI D-Bus call timed out") from exc
        except AccountAiUnavailable:
            raise
        except Exception as exc:
            raise AccountAiUnavailable(f"Meo Account AI D-Bus call failed: {exc}") from exc

    def _variant_factory(self):
        if self._variant_factory_override is not None:
            return self._variant_factory_override
        try:
            from dbus_next import Variant
        except ImportError as exc:
            raise AccountAiUnavailable(
                "python-dbus-next is required for the Meo Account AI broker client"
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
        if isinstance(value, Mapping):
            return factory("a{sv}", self._variant_map(value))
        if isinstance(value, (list, tuple)):
            if not value:
                raise ValueError("empty list argument has no inferable D-Bus element type")
            if all(isinstance(item, str) for item in value):
                return factory("as", list(value))
            raise ValueError("Account AI list arguments must contain strings")
        raise ValueError(f"unsupported D-Bus argument type: {type(value).__name__}")

    def _variant_map(self, values: Mapping[str, Any]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values.items():
            if not isinstance(key, str) or not key:
                raise ValueError("D-Bus argument keys must be non-empty strings")
            if key.lower() in {"apikey", "api_key", "authorization", "credential", "secret"}:
                raise ValueError("provider credentials must never enter the Meo AI broker client")
            result[key] = self._variant(value)
        return result

    @staticmethod
    def _unwrap(value: Any) -> Any:
        if hasattr(value, "signature") and hasattr(value, "value"):
            return DbusNextAccountAiClient._unwrap(value.value)
        if isinstance(value, dict):
            return {str(key): DbusNextAccountAiClient._unwrap(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [DbusNextAccountAiClient._unwrap(item) for item in value]
        return value

    async def _list_connections(self):
        interface = await self._get_interface()
        return self._unwrap(
            await interface.call_list_available_local_ai_connections(MEO_AI_CLIENT_ID)
        )

    def list_connections(self) -> list[Mapping[str, Any]]:
        value = self._run(self._list_connections())
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise AccountAiUnavailable("Meo Account returned an invalid AI connection list")
        return value

    async def _start_operation(self, action: str, encoded_arguments: Mapping[str, object]):
        interface = await self._get_interface()
        return self._unwrap(
            await interface.call_start_local_ai_operation(
                MEO_AI_CLIENT_ID, action, dict(encoded_arguments)
            )
        )

    def start_operation(self, action: str, arguments: Mapping[str, Any]) -> str:
        if action not in {"discover_models", "prepare_inference", "invoke", "deny_inference"}:
            raise ValueError("unsupported Meo Account AI operation")
        encoded = self._variant_map(arguments)
        value = self._run(self._start_operation(action, encoded))
        if not isinstance(value, str) or not value:
            raise AccountAiUnavailable("Meo Account rejected the AI operation")
        return value

    async def _get_request(self, request_id: str):
        interface = await self._get_interface()
        return self._unwrap(await interface.call_get_request(request_id))

    def get_request(self, request_id: str) -> Mapping[str, Any]:
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("request_id is required")
        value = self._run(self._get_request(request_id))
        if not isinstance(value, dict) or not value:
            raise AccountAiUnavailable("Meo Account returned an invalid AI request")
        return value

    async def _wait_request(self, request_id: str):
        interface = await self._get_interface()
        deadline = self._loop.time() + self._operation_timeout
        while True:
            value = self._unwrap(await interface.call_get_request(request_id))
            if not isinstance(value, dict) or not value:
                raise AccountAiUnavailable("Meo Account lost the AI request")
            state = value.get("state")
            if state in _TERMINAL_STATES:
                return value
            if self._loop.time() >= deadline:
                raise AccountAiUnavailable("Meo Account AI operation timed out")
            await asyncio.sleep(self._poll_interval)

    def wait_request(self, request_id: str) -> Mapping[str, Any]:
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("request_id is required")
        return self._run(
            self._wait_request(request_id),
            timeout=self._operation_timeout + self._timeout,
        )

    @staticmethod
    def inference_arguments(
        *,
        connection_id: str,
        model: str,
        purpose: str,
        user_prompt: str,
        system_prompt: str = "",
        data_categories: tuple[str, ...] = ("user_prompt",),
        temperature: float = 0.3,
        max_output_tokens: int = 2048,
    ) -> dict[str, Any]:
        values = {
            "connectionId": connection_id.strip(),
            "model": model.strip(),
            "purpose": purpose.strip(),
            "systemPrompt": system_prompt,
            "userPrompt": user_prompt,
            "dataCategories": list(data_categories),
            "temperature": float(temperature),
            "maxOutputTokens": int(max_output_tokens),
        }
        if not values["connectionId"] or not values["model"] or not values["purpose"]:
            raise ValueError("connection_id, model and purpose are required")
        if not user_prompt.strip():
            raise ValueError("user_prompt is required")
        if len(system_prompt) > 12000 or len(user_prompt) > 40000:
            raise ValueError("Account AI prompt exceeds the broker input limit")
        categories = values["dataCategories"]
        if not categories or len(categories) > 12 or any(
            not isinstance(item, str) or not item for item in categories
        ):
            raise ValueError("data_categories must contain 1 to 12 non-empty strings")
        if not 0 <= values["temperature"] <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if not 1 <= values["maxOutputTokens"] <= 4096:
            raise ValueError("max_output_tokens must be between 1 and 4096")
        return values

    def prepare_inference(self, arguments: Mapping[str, Any]) -> PreparedAccountInference:
        immutable_arguments = dict(arguments)
        request_id = self.start_operation("prepare_inference", immutable_arguments)
        result = self.wait_request(request_id)
        if result.get("state") != "completed":
            raise AccountAiUnavailable(str(result.get("error") or "Account AI preparation failed"))
        consent = result.get("consent")
        if not isinstance(consent, dict):
            raise AccountAiUnavailable("Meo Account returned no inference consent")
        required = {"requestId", "payloadSha256", "confirmationVersion", "provider", "model"}
        if not required.issubset(consent):
            raise AccountAiUnavailable("Meo Account returned an incomplete inference consent")
        return PreparedAccountInference(immutable_arguments, dict(consent), request_id)

    def invoke_prepared(self, prepared: PreparedAccountInference) -> Mapping[str, Any]:
        consent = dict(prepared.consent)
        consent.update({"approved": True, "remember": False})
        arguments = dict(prepared.arguments)
        arguments["consent"] = consent
        request_id = self.start_operation("invoke", arguments)
        result = self.wait_request(request_id)
        if result.get("state") != "completed":
            raise AccountAiUnavailable(str(result.get("error") or "Account AI inference failed"))
        text = result.get("text")
        if not isinstance(text, str) or not text.strip():
            raise AccountAiUnavailable("Meo Account returned an empty inference result")
        return result

    def deny_prepared(self, prepared: PreparedAccountInference) -> Mapping[str, Any]:
        consent = dict(prepared.consent)
        consent.update({"approved": False, "remember": False})
        arguments = dict(prepared.arguments)
        arguments["consent"] = consent
        request_id = self.start_operation("deny_inference", arguments)
        result = self.wait_request(request_id)
        if result.get("state") != "denied":
            raise AccountAiUnavailable(str(result.get("error") or "Account AI denial failed"))
        return result

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

    def __enter__(self) -> "DbusNextAccountAiClient":
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()

    def __del__(self) -> None:
        if not getattr(self, "_closed", True):
            try:
                self.close()
            except Exception:
                pass
