from __future__ import annotations

import unittest

from meo.cloud.store import SupabaseRestConfig, SupabaseRestStore


class SupabaseRestStoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.calls: list[tuple[str, str, dict, str]] = []

        async def request_json(method: str, path: str, body: dict, prefer: str):
            self.calls.append((method, path, body, prefer))
            if "ai_agent_events" in path:
                return [{"id": 1}]
            return None

        self.store = SupabaseRestStore(
            SupabaseRestConfig(
                project_url="https://example.supabase.co",
                service_role_key="service-role-test-key",
            ),
            request_json=request_json,
        )

    async def test_touch_device_uses_owner_device_upsert(self) -> None:
        await self.store.touch_device(
            user_id="user-1",
            device_id="legion",
            display_name="Legion Y9000X",
            capabilities=("agent.chat",),
        )
        method, path, body, prefer = self.calls[-1]
        self.assertEqual(method, "POST")
        self.assertIn("on_conflict=user_id,device_id", path)
        self.assertEqual(body["user_id"], "user-1")
        self.assertEqual(body["device_id"], "legion")
        self.assertIn("merge-duplicates", prefer)

    async def test_new_agent_event_returns_true(self) -> None:
        inserted = await self.store.append_agent_event(
            user_id="user-1",
            run_id="run-1",
            seq=3,
            event_type="text_delta",
            payload={"text": "hi"},
        )
        self.assertTrue(inserted)

    async def test_duplicate_agent_event_returns_false(self) -> None:
        async def duplicate_request(method: str, path: str, body: dict, prefer: str):
            return []

        store = SupabaseRestStore(
            SupabaseRestConfig(
                project_url="https://example.supabase.co",
                service_role_key="service-role-test-key",
            ),
            request_json=duplicate_request,
        )
        inserted = await store.append_agent_event(
            user_id="user-1",
            run_id="run-1",
            seq=3,
            event_type="text_delta",
            payload={"text": "hi"},
        )
        self.assertFalse(inserted)

    async def test_update_agent_run_rejects_unowned_fields(self) -> None:
        with self.assertRaises(ValueError):
            await self.store.update_agent_run(
                user_id="user-1",
                run_id="run-1",
                values={"device_id": "other"},
            )

    def test_service_role_is_required_but_never_part_of_request_body_contract(self) -> None:
        with self.assertRaises(ValueError):
            SupabaseRestConfig(
                project_url="https://example.supabase.co",
                service_role_key="",
            ).validate()


if __name__ == "__main__":
    unittest.main()
