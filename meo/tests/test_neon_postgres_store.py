import unittest
from contextlib import asynccontextmanager

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


if __name__ == "__main__":
    unittest.main()
