import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch

from meo.cloud.postgres_store import NeonPostgresStore


class FakePool:
    def __init__(self, *, row=None, value=None):
        self.row = row
        self.value = value
        self.calls = []

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        return self.row

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        return self.value

    @asynccontextmanager
    async def acquire(self):
        yield self

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return []

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "INSERT 0 1"


class NeonPostgresStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_pool_initial_size_remains_one_with_asyncpg_032(self):
        captured = {}

        async def create_pool(**kwargs):
            captured.update(kwargs)
            return FakePool()

        fake_asyncpg = SimpleNamespace(create_pool=create_pool)
        with patch.dict("sys.modules", {"asyncpg": fake_asyncpg}):
            store = NeonPostgresStore("postgresql://local/test")
            await store._get_pool()

        self.assertEqual(captured["init_size"], 1)
        self.assertEqual(captured["min_size"], 1)
        self.assertEqual(captured["max_size"], 10)

    def test_connection_requires_a_postgres_url(self):
        with self.assertRaisesRegex(ValueError, "PostgreSQL"):
            NeonPostgresStore("https://database.example")

    async def test_conversation_lookup_is_scoped_to_the_account(self):
        pool = FakePool(row={"id": "conversation-id"})
        store = NeonPostgresStore("postgresql://local/test", pool=pool)

        result = await store.get_conversation(user_id="account-a", conversation_id="conversation-id")

        self.assertEqual(result, {"id": "conversation-id"})
        query, args = pool.calls[0][1:]
        self.assertIn("id=$1::uuid and user_id=$2::uuid", query)
        self.assertEqual(args, ("conversation-id", "account-a"))

    async def test_foreign_conversation_cannot_receive_a_message(self):
        pool = FakePool(value=None)
        store = NeonPostgresStore("postgresql://local/test", pool=pool)

        with self.assertRaisesRegex(LookupError, "conversation_not_found"):
            await store.append_conversation_message(
                user_id="account-a", conversation_id="other-account-conversation",
                role="user", content="hello",
            )

        self.assertEqual([call[0] for call in pool.calls], ["fetchval"])

    async def test_agent_run_discovery_is_owner_scoped_and_bounded(self):
        pool = FakePool()
        store = NeonPostgresStore("postgresql://local/test", pool=pool)
        self.assertEqual(await store.list_agent_runs(user_id="owner-a", limit=20), ())
        _, sql, args = pool.calls[0]
        self.assertIn("where user_id=$1::uuid", sql)
        self.assertIn("order by created_at desc,id desc limit $2", sql)
        self.assertNotIn("workspace_ref", sql)
        self.assertNotIn("local_request_id", sql)
        self.assertEqual(args, ("owner-a", 20))
        for invalid in (0, 51, -1, True, 2.5):
            with self.subTest(limit=invalid):
                with self.assertRaises(ValueError):
                    await store.list_agent_runs(user_id="owner-a", limit=invalid)

    async def test_agent_event_insert_is_account_scoped_and_idempotent(self):
        pool = FakePool()
        store = NeonPostgresStore("postgresql://local/test", pool=pool)

        inserted = await store.append_agent_event(
            user_id="account-a", run_id="run-id", seq=3, event_type="message",
            payload={"text": "safe test value"},
        )

        self.assertTrue(inserted)
        _, query, args = pool.calls[0]
        self.assertIn("values($1::uuid,$2::uuid,$3,$4,$5::jsonb)", query)
        self.assertIn("on conflict(run_id,seq) do nothing", query)
        self.assertEqual(args[:4], ("account-a", "run-id", 3, "message"))

    async def test_agent_run_cursor_updates_never_decrease_existing_value(self):
        pool = FakePool()
        store = NeonPostgresStore("postgresql://local/test", pool=pool)
        await store.update_agent_run(
            user_id="account-a", run_id="run-id",
            values={"status": "running", "last_event_seq": 3},
        )
        _, query, args = pool.calls[0]
        self.assertIn("last_event_seq=greatest(coalesce(last_event_seq,-1),$2)", query)
        self.assertIn("where id=$4::uuid and user_id=$5::uuid", query)
        self.assertEqual(args[:2], ("running", 3))

    async def test_status_update_cannot_resurrect_terminal_run(self):
        pool = FakePool()
        store = NeonPostgresStore("postgresql://local/test", pool=pool)
        await store.update_agent_run(
            user_id="account-a", run_id="run-id",
            values={"status": "running"},
        )
        _, sql, args = pool.calls[0]
        self.assertIn("status=case when status in ('completed','cancelled','failed')", sql)
        self.assertIn("then status else $1 end", sql)
        self.assertEqual(args[0], "running")

    async def test_out_of_order_status_cannot_override_newer_cursor(self):
        pool = FakePool()
        store = NeonPostgresStore("postgresql://local/test", pool=pool)
        await store.update_agent_run(
            user_id="account-a", run_id="run-id",
            values={"last_event_seq": 3, "status": "awaiting_approval"},
        )
        _, sql, args = pool.calls[0]
        self.assertIn("coalesce(last_event_seq,-1) > $1", sql)
        self.assertIn("then status else $2 end", sql)
        self.assertIn("last_event_seq=greatest(coalesce(last_event_seq,-1),$1)", sql)
        self.assertEqual(args[:2], (3, "awaiting_approval"))

    async def test_account_grants_are_never_read_from_the_ai_database(self):
        pool = FakePool(value=True)
        store = NeonPostgresStore("postgresql://local/test", pool=pool)
        self.assertFalse(await store.has_recent_reauth(user_id="account-a", session_id="session-a", purpose="account_security"))
        self.assertEqual(pool.calls, [])

    async def test_message_replay_is_owned_ordered_and_bounded(self):
        pool = FakePool()
        store = NeonPostgresStore("postgresql://local/test", pool=pool)
        await store.list_conversation_messages(user_id="account-a", conversation_id="conversation-a", limit=25)
        _, query, args = pool.calls[0]
        self.assertIn("c.user_id=$1::uuid and m.user_id=$1::uuid", query)
        self.assertIn("order by m.created_at asc,m.id asc limit $3", query)
        self.assertEqual(args, ("account-a", "conversation-a", 25))

    async def test_conversation_cursor_stays_scoped_to_the_owner(self):
        pool = FakePool()
        store = NeonPostgresStore("postgresql://local/test", pool=pool)
        await store.list_conversations(user_id="account-a", limit=25, before=("2026-10-15T00:00:00Z", "conversation-a"))
        _, query, args = pool.calls[0]
        self.assertIn("user_id = $1::uuid", query)
        self.assertIn("(updated_at, id) <", query)
        self.assertEqual(args[0], "account-a")
        self.assertEqual(args[-1], 25)


if __name__ == "__main__":
    unittest.main()
