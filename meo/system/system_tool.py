from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable


class CapabilityEffect(str, Enum):
    READ = "read"
    SESSION = "session"
    PERSISTENT = "persistent"
    IRREVERSIBLE = "irreversible"


class CapabilityVerification(str, Enum):
    OWNER_RESULT = "owner-result"
    READ_BACK = "read-back"


class CapabilityMaturity(str, Enum):
    PREVIEW = "preview"
    STABLE = "stable"


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    title: str
    owner: str
    effect: CapabilityEffect
    verification: CapabilityVerification
    maturity: CapabilityMaturity
    requires_confirmation: bool

    @classmethod
    def from_router(cls, value: Mapping[str, Any]) -> "CapabilityDescriptor":
        capability_id = _required_string(value, "id")
        title = _required_string(value, "title")
        owner = _required_string(value, "owner")
        if "." not in capability_id or not owner.startswith("org.meo."):
            raise ValueError("invalid Meo capability namespace")
        if not capability_id.startswith(owner + "."):
            raise ValueError("capability owner does not own the capability namespace")
        try:
            effect = CapabilityEffect(value.get("effect"))
            verification = CapabilityVerification(value.get("verification"))
            maturity = CapabilityMaturity(value.get("maturity"))
        except ValueError as exc:
            raise ValueError("invalid capability metadata enum") from exc
        confirmation = value.get("requiresConfirmation")
        if not isinstance(confirmation, bool):
            raise ValueError("requiresConfirmation must be boolean")
        return cls(
            capability_id=capability_id,
            title=title,
            owner=owner,
            effect=effect,
            verification=verification,
            maturity=maturity,
            requires_confirmation=confirmation,
        )


@dataclass(frozen=True)
class SystemToolRequest:
    capability_id: str
    arguments: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.capability_id, str) or not self.capability_id.strip():
            raise ValueError("capability_id is required")
        if not isinstance(self.arguments, dict):
            raise ValueError("arguments must be an object")
        _validate_transport_value(self.arguments)


@dataclass(frozen=True)
class SystemToolResult:
    router_request_id: str
    state: str
    capability: CapabilityDescriptor
    router_view: dict[str, Any]


@runtime_checkable
class RouterClient(Protocol):
    """Typed client seam for org.meo.AIRouter1.

    Implementations use one durable session-bus connection so Router caller
    binding remains stable across SubmitRequest, GetRequest and DecideRequest.
    The AI agent does not call Router SubmitText.
    """

    def list_capabilities(self) -> list[Mapping[str, Any]]: ...

    def submit_request(self, capability_id: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def get_request(self, request_id: str) -> Mapping[str, Any]: ...

    def decide_request(self, request_id: str, fingerprint: str, approve: bool) -> Mapping[str, Any]: ...


class SystemTool:
    """Unprivileged typed bridge from the agent to the System AI Router.

    This class never grants a capability, never bypasses confirmation and never
    executes an OS action itself. The Router remains authoritative for the
    executable allowlist, exact argument types, caller binding, fingerprints,
    expiry and confirmation policy.
    """

    def __init__(self, router: RouterClient) -> None:
        if not isinstance(router, RouterClient):
            raise TypeError("router does not implement RouterClient")
        self.router = router

    def capabilities(self) -> list[CapabilityDescriptor]:
        descriptors = [CapabilityDescriptor.from_router(item) for item in self.router.list_capabilities()]
        ids = [item.capability_id for item in descriptors]
        if len(ids) != len(set(ids)):
            raise ValueError("Router returned duplicate capability IDs")
        return descriptors

    def invoke(self, request: SystemToolRequest) -> SystemToolResult:
        available = {item.capability_id: item for item in self.capabilities()}
        try:
            descriptor = available[request.capability_id]
        except KeyError as exc:
            raise ValueError("capability is not currently executable") from exc

        # Do not validate or coerce capability-specific argument types here.
        # The Router owns the exact typed schema and must reject mismatches.
        view = dict(self.router.submit_request(request.capability_id, dict(request.arguments)))
        request_id = _required_string(view, "requestId")
        state = _required_string(view, "state")
        return SystemToolResult(request_id, state, descriptor, view)

    def refresh(self, router_request_id: str) -> dict[str, Any]:
        if not isinstance(router_request_id, str) or not router_request_id:
            raise ValueError("router_request_id is required")
        return dict(self.router.get_request(router_request_id))

    def decide(self, router_request_id: str, fingerprint: str, approve: bool) -> dict[str, Any]:
        if not isinstance(router_request_id, str) or not router_request_id:
            raise ValueError("router_request_id is required")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise ValueError("fingerprint is required")
        if not isinstance(approve, bool):
            raise ValueError("approve must be boolean")
        # Explicit decision only. There is deliberately no auto-approve path.
        return dict(self.router.decide_request(router_request_id, fingerprint, approve))


def _required_string(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return item


def _validate_transport_value(value: Any, *, depth: int = 0) -> None:
    if depth > 8:
        raise ValueError("arguments are nested too deeply")
    # D-Bus a{sv} has no transport-neutral null value. Do not invent one here.
    if isinstance(value, (bool, int, float, str)):
        return
    if isinstance(value, list):
        for item in value:
            _validate_transport_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError("argument keys must be non-empty strings")
            _validate_transport_value(item, depth=depth + 1)
        return
    raise ValueError(f"unsupported argument value type: {type(value).__name__}")
