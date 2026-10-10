from __future__ import annotations

import unittest
from unittest.mock import patch
from uuid import uuid4

from meo.cloud.account_auth import AccountIdentity
from meo.cloud.server import CloudServerConfig, build_application


class ConversationStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def list_conversations(self, *, user_id: str, limit: int = 50):
        self.calls.append(("list", user_id))
        return ({"id": str(uuid4()), "title": "Owned", "user_id": user_id},)

    async def create_conversation(self, *, user_id: str, title: str):
        self.calls.append(("create", user_id))
        return {"id": str(uuid4()), "title": title, "user_id": user_id}

    async def get_conversation(self, *, user_id: str, conversation_id: str):
        self.calls.append(("get", user_id))
        return {"id": conversation_id, "user_id": user_id} if user_id == "owner" else None

    async def list_conversation_messages(self, *, user_id: str, conversation_id: str, limit: int = 500):
        self.calls.append(("messages", user_id))
        return ({"id": str(uuid4()), "role": "user", "content": [{"type": "text", "text": "hi"}]},)

    async def append_conversation_message(
        self, *, user_id: str, conversation_id: str, role: str, content: str,
    ):
        self.calls.append(("append", user_id))
        return {"id": str(uuid4()), "role": role, "content": content}


class AccountVerifier:
    async def verify(self, token: str) -> AccountIdentity:
        return AccountIdentity(user_id="owner" if token == "owner-token" else "other")


class ConversationRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_uses_verified_identity_and_rejects_other_users(self) -> None:
        from aiohttp.test_utils import TestClient, TestServer

        store = ConversationStore()
        config = CloudServerConfig(
            supabase_url="https://example.supabase.co",
            supabase_publishable_key="publishable",
            supabase_service_role_key="service-role",
        )
        with (
            patch("meo.cloud.server.SupabaseRestStore", return_value=store),
            patch("meo.cloud.server.SupabaseAccountTokenVerifier", return_value=AccountVerifier()),
        ):
            async with TestClient(TestServer(build_application(config))) as client:
                unauthenticated = await client.get("/v1/conversations")
                self.assertEqual(unauthenticated.status, 401)
                self.assertEqual(
                    await unauthenticated.json(),
                    {"error": {"code": "unauthorized", "message": "Sign in with Meo Account."}},
                )

                missing_route = await client.get("/v1/not-a-route")
                self.assertEqual(missing_route.status, 404)
                self.assertEqual(
                    (await missing_route.json())["error"]["code"],
                    "not_found",
                )

                headers = {"Authorization": "Bearer owner-token"}
                listed = await client.get("/v1/conversations", headers=headers)
                self.assertEqual(listed.status, 200)
                self.assertEqual(store.calls[-1], ("list", "owner"))

                created = await client.post(
                    "/v1/conversations",
                    headers=headers,
                    json={"title": "Saved from chat", "user_id": "other"},
                )
                self.assertEqual(created.status, 400)
                created = await client.post(
                    "/v1/conversations",
                    headers=headers,
                    json={"title": "Saved from chat"},
                )
                self.assertEqual(created.status, 201)
                self.assertEqual(store.calls[-1], ("create", "owner"))

                conversation_id = str(uuid4())
                wrong_owner = await client.get(
                    f"/v1/conversations/{conversation_id}/messages",
                    headers={"Authorization": "Bearer other-token"},
                )
                self.assertEqual(wrong_owner.status, 404)
                self.assertNotIn(("append", "other"), store.calls)

                saved = await client.post(
                    f"/v1/conversations/{conversation_id}/messages",
                    headers=headers,
                    json={"role": "user", "content": "Hello"},
                )
                self.assertEqual(saved.status, 201)
                self.assertEqual(store.calls[-1], ("append", "owner"))


if __name__ == "__main__":
    unittest.main()
