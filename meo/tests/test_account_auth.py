from __future__ import annotations

import base64
import json
import unittest

from meo.cloud.account_auth import (
    SupabaseAccountAuthConfig,
    SupabaseAccountTokenVerifier,
)


def jwt_with_session(session_id: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"session_id": session_id}).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"header.{payload}.signature"


class AccountAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_verified_account_subject_comes_from_auth_service(self) -> None:
        seen: list[str] = []

        async def request_user(token: str):
            seen.append(token)
            return {"id": "user-1", "email": "user@example.test"}

        token = jwt_with_session("session-1")
        verifier = SupabaseAccountTokenVerifier(
            SupabaseAccountAuthConfig(
                project_url="https://example.supabase.co",
                publishable_key="sb_publishable_test",
            ),
            request_user=request_user,
        )
        identity = await verifier.verify(token)
        self.assertEqual(seen, [token])
        self.assertEqual(identity.user_id, "user-1")
        self.assertEqual(identity.email, "user@example.test")
        self.assertEqual(identity.session_id, "session-1")

    async def test_non_jwt_token_can_still_authenticate_without_session_binding(self) -> None:
        verifier = SupabaseAccountTokenVerifier(
            SupabaseAccountAuthConfig(
                project_url="https://example.supabase.co",
                publishable_key="sb_publishable_test",
            ),
            request_user=lambda _token: {"id": "user-1"},
        )
        identity = await verifier.verify("opaque-access-token")
        self.assertIsNone(identity.session_id)

    async def test_missing_subject_is_rejected(self) -> None:
        verifier = SupabaseAccountTokenVerifier(
            SupabaseAccountAuthConfig(
                project_url="https://example.supabase.co",
                publishable_key="sb_publishable_test",
            ),
            request_user=lambda _token: {},
        )
        with self.assertRaises(PermissionError):
            await verifier.verify("access-token")

    async def test_empty_bearer_is_rejected_before_network(self) -> None:
        calls = 0

        def request_user(_token: str):
            nonlocal calls
            calls += 1
            return {"id": "user-1"}

        verifier = SupabaseAccountTokenVerifier(
            SupabaseAccountAuthConfig(
                project_url="https://example.supabase.co",
                publishable_key="sb_publishable_test",
            ),
            request_user=request_user,
        )
        with self.assertRaises(PermissionError):
            await verifier.verify("   ")
        self.assertEqual(calls, 0)


if __name__ == "__main__":
    unittest.main()
