from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from meo.cloud.orchestrator import AgentRunOrchestrator, AgentRunRequest
from meo.cloud.policy import PermissionMode
from meo.cloud.relay import RelayRegistry
from meo.cloud.routing import (
    DeviceSelectionRequired,
    NoEligibleDevice,
    ProjectLocationRequired,
)
from meo.cloud.store import CloudStore


@dataclass(frozen=True)
class ApiError(Exception):
    code: str
    message: str
    status: int = 400
    details: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
        if self.details:
            body["error"]["details"] = self.details
        return body


_CREATE_FIELDS = frozenset(
    {
        "conversation_id",
        "text",
        "project_id",
        "preferred_device_id",
        "permission_mode",
    }
)


class AgentRunApi:
    """Transport-neutral product API for Web and Native clients.

    Callers authenticate outside this class and pass only the verified account
    subject as `user_id`. Local paths, shell commands, credentials and service
    secrets are intentionally not part of the public request schema.
    """

    def __init__(
        self,
        *,
        store: CloudStore,
        relay: RelayRegistry,
        orchestrator: AgentRunOrchestrator,
    ) -> None:
        self.store = store
        self.relay = relay
        self.orchestrator = orchestrator

    async def create(
        self,
        *,
        user_id: str,
        payload: dict[str, Any],
        allow_full_access: bool = False,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ApiError("invalid_request", "Request body must be an object.")
        unknown = set(payload) - _CREATE_FIELDS
        if unknown:
            raise ApiError(
                "unsupported_fields",
                "This request contains fields Meo AI does not accept.",
                details={"fields": sorted(unknown)},
            )

        try:
            mode = PermissionMode(str(payload.get("permission_mode", "smart")))
        except ValueError as exc:
            raise ApiError("invalid_permission_mode", "Choose Ask, Smart, or Full Access.") from exc

        try:
            request = AgentRunRequest(
                conversation_id=self._required_text(payload, "conversation_id"),
                text=self._required_text(payload, "text"),
                project_id=self._optional_text(payload.get("project_id")),
                preferred_device_id=self._optional_text(payload.get("preferred_device_id")),
                permission_mode=mode,
            )
            created = await self.orchestrator.create_and_dispatch(
                user_id=user_id,
                request=request,
                allow_full_access=allow_full_access,
            )
        except DeviceSelectionRequired as exc:
            raise ApiError(
                "device_selection_required",
                "Choose which of your online devices should run this task.",
                status=409,
                details={"device_ids": list(exc.device_ids)},
            ) from exc
        except ProjectLocationRequired as exc:
            raise ApiError(
                "project_location_required",
                "Open this project once on a trusted device to connect its workspace.",
                status=409,
            ) from exc
        except NoEligibleDevice as exc:
            raise ApiError(
                "no_online_device",
                "No suitable Meo device is online right now.",
                status=409,
            ) from exc
        except PermissionError as exc:
            if mode is PermissionMode.FULL_ACCESS and not allow_full_access:
                raise ApiError(
                    "full_access_not_authorized",
                    "Full Access must be enabled from a trusted device first.",
                    status=403,
                ) from exc
            raise ApiError("not_allowed", "This task is not allowed.", status=403) from exc
        except ValueError as exc:
            raise ApiError("invalid_request", str(exc)) from exc

        return {
            "run_id": created.run_id,
            "status": created.status,
            "device_id": created.device_id,
            "permission_mode": created.permission_mode.value,
        }

    async def cancel(self, *, user_id: str, run_id: str) -> dict[str, Any]:
        run = await self._owned_run(user_id=user_id, run_id=run_id)
        status = str(run.get("status", ""))
        if status in {"completed", "cancelled", "failed"}:
            return {"run_id": run_id, "status": status}
        device_id = self._run_device_id(run)
        try:
            await self.relay.cancel_agent_run(
                account_user_id=user_id,
                device_id=device_id,
                run_id=run_id,
            )
        except ConnectionError as exc:
            raise ApiError(
                "device_offline",
                "The device went offline before cancellation could be delivered.",
                status=409,
            ) from exc
        await self.store.update_agent_run(
            user_id=user_id,
            run_id=run_id,
            values={"status": "cancel_requested"},
        )
        return {"run_id": run_id, "status": "cancel_requested"}

    async def decide(
        self,
        *,
        user_id: str,
        run_id: str,
        decision_id: str,
        option_index: int,
    ) -> dict[str, Any]:
        run = await self._owned_run(user_id=user_id, run_id=run_id)
        if run.get("status") != "awaiting_approval":
            raise ApiError(
                "approval_not_pending",
                "This task is not waiting for a decision.",
                status=409,
            )
        if not isinstance(option_index, int) or isinstance(option_index, bool) or option_index < 0:
            raise ApiError("invalid_decision", "Choose a valid approval option.")
        decision_id = decision_id.strip()
        if not decision_id:
            raise ApiError("invalid_decision", "decision_id is required.")

        device_id = self._run_device_id(run)
        try:
            await self.relay.submit_decision(
                account_user_id=user_id,
                device_id=device_id,
                run_id=run_id,
                decision_id=decision_id,
                option_index=option_index,
            )
        except ConnectionError as exc:
            raise ApiError(
                "device_offline",
                "The device went offline before your decision could be delivered.",
                status=409,
            ) from exc
        return {"run_id": run_id, "decision_id": decision_id, "accepted": True}

    async def _owned_run(self, *, user_id: str, run_id: str) -> dict[str, Any]:
        run_id = run_id.strip()
        if not run_id:
            raise ApiError("invalid_request", "run_id is required.")
        run = await self.store.get_agent_run(user_id=user_id, run_id=run_id)
        if run is None:
            # Do not reveal whether a run exists for another account.
            raise ApiError("run_not_found", "Agent task not found.", status=404)
        return run

    @staticmethod
    def _run_device_id(run: dict[str, Any]) -> str:
        device_id = run.get("device_id")
        if not isinstance(device_id, str) or not device_id.strip():
            raise ApiError("invalid_run_state", "Agent task has no valid device.", status=500)
        return device_id.strip()

    @staticmethod
    def _required_text(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ApiError("invalid_request", f"{key} is required.")
        return value.strip()

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ApiError("invalid_request", "Optional text fields must be non-empty strings.")
        return value.strip()
