from __future__ import annotations

import unittest

from meo.cloud.relay import RelayRegistry, RelaySession
from meo.cloud.routing import (
    AutomaticDeviceResolver,
    DeviceSelectionRequired,
    NoEligibleDevice,
    ProjectLocationRequired,
)


class FakeConnection:
    async def send_json(self, payload: dict) -> None:
        pass


class FakeStore:
    def __init__(self, locations=()):
        self.locations = tuple(locations)

    async def list_project_locations(self, *, user_id: str, project_id: str):
        return self.locations


class AutomaticDeviceResolverTests(unittest.IsolatedAsyncioTestCase):
    def registry_with(self, *device_ids: str) -> RelayRegistry:
        registry = RelayRegistry()
        for device_id in device_ids:
            registry.register(
                RelaySession("user-1", device_id, ("agent.chat",)),
                FakeConnection(),
            )
        return registry

    async def test_single_online_device_is_selected_automatically(self) -> None:
        resolver = AutomaticDeviceResolver(FakeStore(), self.registry_with("legion"))
        result = await resolver.resolve(
            user_id="user-1",
            project_id=None,
            preferred_device_id=None,
            required_capability="agent.chat",
        )
        self.assertEqual(result.device_id, "legion")
        self.assertIsNone(result.workspace_ref)

    async def test_multiple_online_devices_require_one_simple_choice(self) -> None:
        resolver = AutomaticDeviceResolver(
            FakeStore(), self.registry_with("legion", "macbook")
        )
        with self.assertRaises(DeviceSelectionRequired) as raised:
            await resolver.resolve(
                user_id="user-1",
                project_id=None,
                preferred_device_id=None,
                required_capability="agent.chat",
            )
        self.assertEqual(raised.exception.device_ids, ("legion", "macbook"))

    async def test_project_workspace_only_comes_from_saved_mapping(self) -> None:
        resolver = AutomaticDeviceResolver(
            FakeStore(
                [
                    {
                        "device_id": "legion",
                        "workspace_ref": "workspace-meo-ai",
                    }
                ]
            ),
            self.registry_with("legion"),
        )
        result = await resolver.resolve(
            user_id="user-1",
            project_id="project-1",
            preferred_device_id=None,
            required_capability="agent.chat",
        )
        self.assertEqual(result.device_id, "legion")
        self.assertEqual(result.workspace_ref, "workspace-meo-ai")

    async def test_project_without_saved_location_does_not_fall_back_to_arbitrary_path(self) -> None:
        resolver = AutomaticDeviceResolver(FakeStore(), self.registry_with("legion"))
        with self.assertRaises(ProjectLocationRequired):
            await resolver.resolve(
                user_id="user-1",
                project_id="project-1",
                preferred_device_id=None,
                required_capability="agent.chat",
            )

    async def test_other_accounts_devices_are_not_candidates(self) -> None:
        registry = RelayRegistry()
        registry.register(
            RelaySession("other-user", "other-device", ("agent.chat",)),
            FakeConnection(),
        )
        resolver = AutomaticDeviceResolver(FakeStore(), registry)
        with self.assertRaises(NoEligibleDevice):
            await resolver.resolve(
                user_id="user-1",
                project_id=None,
                preferred_device_id=None,
                required_capability="agent.chat",
            )


if __name__ == "__main__":
    unittest.main()
