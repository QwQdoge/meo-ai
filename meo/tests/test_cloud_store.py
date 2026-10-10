from __future__ import annotations

import unittest

from meo.cloud.store import SupabaseRestConfig, SupabaseRestStore


class SupabaseRestStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_event_replay_query_is_owned_ordered_and_bounded(self):
        await self.store.list_agent_events(user_id="user-1", run_id="run-1", after=4)
        from urllib.parse import parse_qs, urlsplit
        method, path, body, _prefer = self.calls[-1]
        query = parse_qs(urlsplit(path).query)
        self.assertEqual(method, "GET")
        self.assertIsNone(body)
        self.assertEqual(query["user_id"], ["eq.user-1"])
        self.assertEqual(query["run_id"], ["eq.run-1"])
        self.assertEqual(query["seq"], ["gt.4"])
        self.assertEqual(query["order"], ["seq.asc"])
        self.assertEqual(query["limit"], ["100"])
        for after in (-2, True):
            with self.assertRaises(ValueError):
                await self.store.list_agent_events(user_id="user-1", run_id="run-1", after=after)

    async def test_conversation_and_message_queries_are_owner_scoped(self) -> None:
        async def conversation_request(method: str, path: str, body: dict | None, prefer: str | None):
            self.calls.append((method, path, body, prefer))
            if method == "POST" and "ai_conversations" in path:
                return [{"id": "conversation-1", "user_id": "user-1", "title": "Hello"}]
            if method == "POST" and "ai_messages" in path:
                return [{"id": "message-1", "role": "user", "content": body["content"]}]
            if method == "GET" and "ai_conversations" in path:
                return [{"id": "conversation-1", "title": "Hello"}]
            if method == "GET" and "ai_messages" in path:
                return [{"id": "message-1", "role": "user"}]
            return None

        self.store = SupabaseRestStore(
            SupabaseRestConfig(
                project_url="https://example.supabase.co",
                service_role_key="service-role-test-key",
            ),
            request_json=conversation_request,
        )
        from urllib.parse import parse_qs, urlsplit

        conversations = await self.store.list_conversations(user_id="user-1")
        query = parse_qs(urlsplit(self.calls[-1][1]).query)
        self.assertEqual(query["user_id"], ["eq.user-1"])
        self.assertEqual(conversations[0]["id"], "conversation-1")

        conversation = await self.store.create_conversation(user_id="user-1", title="  Hello  ")
        self.assertEqual(self.calls[-1][2], {"user_id": "user-1", "title": "Hello"})
        self.assertEqual(conversation["id"], "conversation-1")

        messages = await self.store.list_conversation_messages(
            user_id="user-1",
            conversation_id="conversation-1",
        )
        query = parse_qs(urlsplit(self.calls[-1][1]).query)
        self.assertEqual(query["user_id"], ["eq.user-1"])
        self.assertEqual(query["conversation_id"], ["eq.conversation-1"])
        self.assertEqual(messages[0]["id"], "message-1")

        saved = await self.store.append_conversation_message(
            user_id="user-1",
            conversation_id="conversation-1",
            role="user",
            content="Hello",
        )
        message_call = self.calls[-2]
        assert message_call[2] is not None
        self.assertEqual(message_call[2]["user_id"], "user-1")
        self.assertEqual(message_call[2]["content"], [{"type": "text", "text": "Hello"}])
        self.assertEqual(saved["id"], "message-1")
        self.assertIn("user_id=eq.user-1", self.calls[-1][1])

    def setUp(self) -> None:
        self.calls: list[tuple[str, str, dict | None, str | None]] = []

        async def request_json(method: str, path: str, body: dict | None, prefer: str | None):
            self.calls.append((method, path, body, prefer))
            if "ai_agent_events" in path:
                return [{"id": 1}]
            if "ai_project_locations" in path:
                return [{"device_id": "legion", "workspace_ref": "workspace-meo-ai"}]
            if "ai_agent_runs" in path and method == "GET":
                return [{"id": "run-1", "device_id": "legion", "status": "running"}]
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
        assert body is not None
        self.assertEqual(body["user_id"], "user-1")
        self.assertEqual(body["device_id"], "legion")
        assert prefer is not None
        self.assertIn("merge-duplicates", prefer)

    async def test_agent_run_persists_permission_and_server_routed_workspace(self) -> None:
        await self.store.create_agent_run(
            run_id="run-1",
            user_id="user-1",
            conversation_id=None,
            device_id="legion",
            status="queued",
            project_id="project-1",
            workspace_ref="workspace-meo-ai",
            permission_mode="smart",
            requested_capabilities=("agent.chat",),
        )
        _method, _path, body, _prefer = self.calls[-1]
        assert body is not None
        self.assertEqual(body["permission_mode"], "smart")
        self.assertEqual(body["requested_capabilities"], ["agent.chat"])
        self.assertEqual(body["workspace_ref"], "workspace-meo-ai")
        self.assertNotIn("/", body["workspace_ref"])

    async def test_project_location_read_is_explicitly_owner_scoped(self) -> None:
        rows = await self.store.list_project_locations(
            user_id="user-1",
            project_id="project-1",
        )
        method, path, body, prefer = self.calls[-1]
        self.assertEqual(method, "GET")
        self.assertIsNone(body)
        self.assertIsNone(prefer)
        self.assertIn("user_id=eq.user-1", path)
        self.assertIn("project_id=eq.project-1", path)
        self.assertEqual(rows[0]["device_id"], "legion")
        self.assertEqual(rows[0]["workspace_ref"], "workspace-meo-ai")

    async def test_get_agent_run_is_owner_scoped(self) -> None:
        row = await self.store.get_agent_run(user_id="user-1", run_id="run-1")
        _method, path, _body, _prefer = self.calls[-1]
        self.assertIn("user_id=eq.user-1", path)
        self.assertIn("id=eq.run-1", path)
        assert row is not None
        self.assertEqual(row["device_id"], "legion")

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
        async def duplicate_request(method: str, path: str, body: dict | None, prefer: str | None):
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
