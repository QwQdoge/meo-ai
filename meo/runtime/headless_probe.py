from __future__ import annotations

from dataclasses import dataclass
import sys
from types import ModuleType
from typing import Iterable


FORBIDDEN_MODULE_PREFIXES = (
    "gi.repository.Gtk",
    "gi.repository.Adw",
    "gi.repository.WebKit",
    "gi.repository.WebKit2",
    "src.ui",
    "src.ui_controller",
)


@dataclass(frozen=True)
class HeadlessProbeResult:
    forbidden_modules: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.forbidden_modules

    def require_clean(self) -> None:
        if self.forbidden_modules:
            joined = ", ".join(self.forbidden_modules)
            raise RuntimeError(f"headless runtime imported forbidden UI modules: {joined}")


def _is_forbidden(name: str) -> bool:
    return any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN_MODULE_PREFIXES)


def inspect_loaded_modules(module_names: Iterable[str] | None = None) -> HeadlessProbeResult:
    names = tuple(module_names) if module_names is not None else tuple(sys.modules)
    forbidden = tuple(sorted(name for name in names if _is_forbidden(name)))
    return HeadlessProbeResult(forbidden)


def require_headless() -> None:
    inspect_loaded_modules().require_clean()
