from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Iterable

from .backend_adapter import ModelInfo


@dataclass(frozen=True)
class ModelRoleSpec:
    role_id: str
    label: str
    description: str
    workload: str


MODEL_ROLE_SPECS = (
    ModelRoleSpec(
        "chat",
        "Chat",
        "Default conversational model for ordinary requests that do not need tools or deep reasoning.",
        "primary",
    ),
    ModelRoleSpec(
        "reasoning",
        "Reasoning",
        "Primary model for planning, difficult reasoning, analysis, and composing complex answers.",
        "primary",
    ),
    ModelRoleSpec(
        "execution",
        "Execution",
        "Tool-capable model used for coding, bounded agent steps, and implementation work.",
        "primary",
    ),
    ModelRoleSpec(
        "vision",
        "Vision",
        "Multimodal model selected when the request contains an image resource.",
        "primary",
    ),
    ModelRoleSpec(
        "judge",
        "Judge",
        "Small structured-output model for verification, ranking, and routing choices.",
        "auxiliary",
    ),
    ModelRoleSpec(
        "title",
        "Title & summary",
        "Cheap background model for chat titles, short labels, and summaries.",
        "auxiliary",
    ),
)


class ModelRoleRegistry:
    """Non-secret model-role assignments owned by AgentService.

    Providers and credentials stay behind the backend boundary. The registry
    only stores stable model IDs and can expose whether the current backend has
    request-scoped routing support.
    """

    def __init__(self, storage_path: str | os.PathLike[str] | None = None) -> None:
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self._assignments: dict[str, str] = {}
        self._load()

    @property
    def role_ids(self) -> set[str]:
        return {item.role_id for item in MODEL_ROLE_SPECS}

    def _load(self) -> None:
        if self.storage_path is None or not self.storage_path.exists():
            return
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return
        assignments = payload.get("assignments") if isinstance(payload, dict) else None
        if not isinstance(assignments, dict):
            return
        for role_id, model_id in assignments.items():
            if role_id in self.role_ids and isinstance(model_id, str) and model_id.strip():
                self._assignments[role_id] = model_id.strip()

    def _save(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.storage_path.with_suffix(self.storage_path.suffix + ".tmp")
        payload = {"version": 2, "assignments": self._assignments}
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        os.replace(temp, self.storage_path)

    @staticmethod
    def _model_list(models: Iterable[ModelInfo]) -> list[ModelInfo]:
        return list(models)

    @staticmethod
    def _fallback_model_id(models: Iterable[ModelInfo]) -> str:
        available = list(models)
        return next((item.model_id for item in available if item.selected), available[0].model_id if available else "")

    def resolve_model(self, role_id: str, models: Iterable[ModelInfo]) -> tuple[str, bool]:
        if role_id not in self.role_ids:
            raise ValueError(f"unknown model role: {role_id}")
        available = self._model_list(models)
        available_ids = {item.model_id for item in available}
        preferred = self._assignments.get(role_id, "")
        if preferred and preferred in available_ids:
            return preferred, False
        fallback = self._fallback_model_id(available)
        if not fallback:
            raise ValueError("no model is available for routing")
        return fallback, bool(preferred)

    def list_roles(self, models: Iterable[ModelInfo]) -> list[dict]:
        available = self._model_list(models)
        available_ids = {item.model_id for item in available}
        selected_id = self._fallback_model_id(available)
        runtime_supported = bool(available) and all(item.selection_scope == "request" for item in available)
        result = []
        for spec in MODEL_ROLE_SPECS:
            preferred = self._assignments.get(spec.role_id, "")
            result.append(
                {
                    "role_id": spec.role_id,
                    "label": spec.label,
                    "description": spec.description,
                    "workload": spec.workload,
                    "preferred_model_id": preferred,
                    "preferred_available": bool(preferred and preferred in available_ids),
                    "fallback_model_id": selected_id,
                    "runtime_supported": runtime_supported,
                    "routing_status": "active" if runtime_supported else "preference_only",
                    "selection_scope": "request" if runtime_supported else "profile",
                }
            )
        return result

    def set_role(self, role_id: str, model_id: str | None, models: Iterable[ModelInfo]) -> dict:
        if role_id not in self.role_ids:
            raise ValueError(f"unknown model role: {role_id}")
        available = self._model_list(models)
        available_ids = {item.model_id for item in available}
        if model_id is None or not model_id.strip():
            self._assignments.pop(role_id, None)
        else:
            normalized = model_id.strip()
            if normalized not in available_ids:
                raise ValueError(f"unknown model_id: {normalized}")
            self._assignments[role_id] = normalized
        self._save()
        return next(item for item in self.list_roles(available) if item["role_id"] == role_id)


def default_model_role_path() -> Path:
    configured = os.environ.get("XDG_CONFIG_HOME")
    base = Path(configured).expanduser() if configured else Path.home() / ".config"
    return base / "meo-ai" / "model-roles.json"
