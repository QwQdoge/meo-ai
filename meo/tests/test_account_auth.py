from __future__ import annotations

import unittest

from meo.cloud.account_auth import (
    SupabaseAccountAuthConfig,
    SupabaseAccountTokenVerifier,
)


class AccountAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_verified_account_subject_comes_from_auth_service(self) -> None:
        seen: list[str] = []

        async def request_user(token: str):
            seen.append(token)
            return {"id": "user-1", "email": "user@example.test"}

        verifier = SupabaseAccountTokenVerifier(
            SupabaseAccountAuthConfig(
                project_url="https://example.supabase.co",
                publishable_key="sb_publishable_test",
            ),
            request_user=request_user,
        )
        identity = await verifier.verify("access-token")
        self.assertEqual(seen, ["access-token"])
        self.assertEqual(identity.user_id, "user-1")
        self.assertEqual(identity.email, "user@example.test")

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
