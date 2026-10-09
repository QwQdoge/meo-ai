from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
import unittest

from meo.cloud.device_auth import DeviceBearerVerifier


class FakeStore:
    def __init__(self, row=None) -> None:
        self.row = row
        self.hashes: list[str] = []

    async def get_device_credential_by_hash(self, *, token_hash: str):
        self.hashes.append(token_hash)
        return self.row


class DeviceAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_plaintext_token_is_hashed_before_store_lookup(self) -> None:
        now = datetime.now(timezone.utc)
        store = FakeStore(
            {
                "id": "cred-1",
                "user_id": "user-1",
                "device_id": "legion",
                "scopes": ["relay.connect", "agent.receive"],
                "issued_at": (now - timedelta(minutes=1)).isoformat(),
                "expires_at": (now + timedelta(days=30)).isoformat(),
                "revoked_at": None,
            }
        )
        verifier = DeviceBearerVerifier(store)  # type: ignore[arg-type]
        claims = await verifier.verify("secret-device-token")
        expected = hashlib.sha256(b"secret-device-token").hexdigest()
        self.assertEqual(store.hashes, [expected])
        self.assertNotEqual(store.hashes[0], "secret-device-token")
        self.assertEqual(claims.device_id, "legion")
        self.assertTrue(claims.allows("relay.connect"))

    async def test_unknown_token_is_rejected_without_identity_leak(self) -> None:
        verifier = DeviceBearerVerifier(FakeStore())  # type: ignore[arg-type]
        with self.assertRaises(PermissionError):
            await verifier.verify("unknown-token")

    async def test_expired_credential_is_rejected(self) -> None:
        now = datetime.now(timezone.utc)
        store = FakeStore(
            {
                "id": "cred-1",
                "user_id": "user-1",
                "device_id": "legion",
                "scopes": ["relay.connect"],
                "issued_at": (now - timedelta(days=2)).isoformat(),
                "expires_at": (now - timedelta(days=1)).isoformat(),
                "revoked_at": None,
            }
        )
        verifier = DeviceBearerVerifier(store)  # type: ignore[arg-type]
        with self.assertRaises(PermissionError):
            await verifier.verify("expired-token")


if __name__ == "__main__":
    unittest.main()
