from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol, runtime_checkable


CONTROL_KINDS = {"toggle", "integer", "select", "readonly"}
CONTROL_SCOPES = {"request", "conversation", "profile", "device", "account"}


@dataclass(frozen=True)
class ControlOption:
    value: str
    label: str

    def public_dict(self) -> dict[str, str]:
        return {"value": self.value, "label": self.label}


@dataclass(frozen=True)
class AiControl:
    control_id: str
    label: str
    kind: str
    value: Any
    description: str = ""
    scope: str = "profile"
    writable: bool = True
    options: tuple[ControlOption, ...] = field(default_factory=tuple)
    minimum: int | None = None
    maximum: int | None = None
    step: int | None = None
    restart_required: bool = False
    safety_note: str = ""

    def __post_init__(self) -> None:
        if not self.control_id or not isinstance(self.control_id, str):
            raise ValueError("control_id is required")
        if self.kind not in CONTROL_KINDS:
            raise ValueError("unsupported control kind")
        if self.scope not in CONTROL_SCOPES:
            raise ValueError("unsupported control scope")
        if self.kind == "toggle" and not isinstance(self.value, bool):
            raise ValueError("toggle control value must be boolean")
        if self.kind == "integer" and (isinstance(self.value, bool) or not isinstance(self.value, int)):
            raise ValueError("integer control value must be integer")
        if self.kind == "select":
            values = {item.value for item in self.options}
            if not values:
                raise ValueError("select control requires options")
            if self.value not in values:
                raise ValueError("select control value is not in options")

    def public_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "control_id": self.control_id,
            "label": self.label,
            "kind": self.kind,
            "value": self.value,
            "description": self.description,
            "scope": self.scope,
            "writable": self.writable,
            "restart_required": self.restart_required,
        }
        if self.options:
            result["options"] = [item.public_dict() for item in self.options]
        if self.minimum is not None:
            result["minimum"] = self.minimum
        if self.maximum is not None:
            result["maximum"] = self.maximum
        if self.step is not None:
            result["step"] = self.step
        if self.safety_note:
            result["safety_note"] = self.safety_note
        return result

    def validate_value(self, value: Any) -> Any:
        if not self.writable or self.kind == "readonly":
            raise ValueError("control is read-only")
        if self.kind == "toggle":
            if not isinstance(value, bool):
                raise ValueError("control value must be boolean")
            return value
        if self.kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("control value must be integer")
            if self.minimum is not None and value < self.minimum:
                raise ValueError("control value is below minimum")
            if self.maximum is not None and value > self.maximum:
                raise ValueError("control value is above maximum")
            return value
        if self.kind == "select":
            if not isinstance(value, str):
                raise ValueError("control value must be a string")
            if value not in {item.value for item in self.options}:
                raise ValueError("control value is not supported")
            return value
        raise ValueError("control is read-only")


@runtime_checkable
class ControlBackend(Protocol):
    """Optional backend extension for user-visible AI runtime controls."""

    def list_controls(self) -> Iterable[AiControl]: ...

    def set_control(self, control_id: str, value: Any) -> AiControl: ...


def find_control(controls: Iterable[AiControl], control_id: str) -> AiControl:
    for control in controls:
        if control.control_id == control_id:
            return control
    raise ValueError(f"unknown control_id: {control_id}")
