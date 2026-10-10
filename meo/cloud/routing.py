from __future__ import annotations

from dataclasses import dataclass

from meo.cloud.orchestrator import ResolvedDevice
from meo.cloud.relay import RelayRegistry
from meo.cloud.store import CloudStore


class DeviceSelectionRequired(RuntimeError):
    def __init__(self, device_ids: tuple[str, ...]) -> None:
        super().__init__("More than one eligible device is online")
        self.device_ids = device_ids


class NoEligibleDevice(RuntimeError):
    pass


class ProjectLocationRequired(RuntimeError):
    pass


@dataclass
class AutomaticDeviceResolver:
    store: CloudStore
    relay: RelayRegistry

    async def resolve(
        self,
        *,
        user_id: str,
        project_id: str | None,
        preferred_device_id: str | None,
        required_capability: str,
    ) -> ResolvedDevice:
        online = {
            session.device_id: session
            for session in self.relay.online_sessions(
                account_user_id=user_id,
                required_capability=required_capability,
            )
        }

        if project_id is not None:
            locations = await self.store.list_project_locations(
                user_id=user_id,
                project_id=project_id,
            )
            if not locations:
                raise ProjectLocationRequired("This project has no saved device location")

            eligible = [
                row for row in locations if row.get("device_id") in online
            ]
            if preferred_device_id is not None:
                for row in eligible:
                    if row.get("device_id") == preferred_device_id:
                        return ResolvedDevice(
                            preferred_device_id,
                            str(row.get("workspace_ref") or "").strip() or None,
                        )
                raise NoEligibleDevice("Preferred device is not online for this project")

            if len(eligible) == 1:
                row = eligible[0]
                return ResolvedDevice(
                    str(row["device_id"]),
                    str(row.get("workspace_ref") or "").strip() or None,
                )
            if len(eligible) > 1:
                raise DeviceSelectionRequired(
                    tuple(sorted(str(row["device_id"]) for row in eligible))
                )
            raise NoEligibleDevice("No saved project device is currently online")

        if preferred_device_id is not None:
            if preferred_device_id in online:
                return ResolvedDevice(preferred_device_id)
            raise NoEligibleDevice("Preferred device is not online")

        if len(online) == 1:
            return ResolvedDevice(next(iter(online)))
        if len(online) > 1:
            raise DeviceSelectionRequired(tuple(sorted(online)))
        raise NoEligibleDevice("No eligible device is online")
