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
        "title",
        "Title",
        "Cheap background model for chat titles and short labels.",
        "auxiliary",
    ),
    ModelRoleSpec(
        "judge",
        "Judge",
        "Small structured-output model for yes/no, ranking, and routing choices.",
        "auxiliary",
    ),
    ModelRoleSpec(
        "reasoning",
        "Reasoning",
        "Primary model for planning, difficult reasoning, and composing the answer.",
        "primary",
    ),
    ModelRoleSpec(
        "execution",
        "Execution",
        "Tool-capable model used for bounded agent steps and implementation work.",
        "primary",
    ),
)


class ModelRoleRegistry:
    """Non-secret model-role preferences owned by AgentService.

    This registry deliberately does not hold provider credentials and does not
    pretend the current Newelle compatibility backend can route one request to
    several models at once. It stores preferences now so the native UI and the
    future Account/provider broker have a stable contract to target.
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
        payload = {"version": 1, "assignments": self._assignments}
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        os.replace(temp, self.storage_path)

    @staticmethod
    def _model_list(models: Iterable[ModelInfo]) -> list[ModelInfo]:
        return list(models)

    def list_roles(self, models: Iterable[ModelInfo]) -> list[dict]:
        available = self._model_list(models)
        available_ids = {item.model_id for item in available}
        selected_id = next((item.model_id for item in available if item.selected), "")
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
                    # The current compatibility backend still has one profile-scoped
                    # model selection. Keep this explicit so UI never implies that
                    # multi-model execution is already active.
                    "runtime_supported": False,
                    "routing_status": "preference_only",
                    "selection_scope": "profile",
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
