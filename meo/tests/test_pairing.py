from __future__ import annotations

import hashlib
import unittest
from datetime import datetime, timedelta, timezone

from meo.cloud.account_auth import AccountIdentity
from meo.cloud.pairing import DevicePairingService


class FakePairingStore:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.by_code: dict[str, str] = {}
        self.reauth = True
        self.consumed: list[dict] = []

    async def create_device_enrollment(self, **values) -> None:
        row = {
            "id": values["enrollment_id"],
            "user_id": None,
            "secret_hash": values["secret_hash"],
            "user_code": values["user_code"],
            "device_id": values["device_id"],
            "display_name": values["display_name"],
            "capabilities": list(values["capabilities"]),
            "requested_scopes": list(values["requested_scopes"]),
            "state": "pending",
            "expires_at": values["expires_at"].isoformat(),
            "approved_at": None,
            "consumed_at": None,
        }
        self.rows[row["secret_hash"]] = row
        self.by_code[row["user_code"]] = row["secret_hash"]

    async def get_device_enrollment_by_code(self, *, user_code: str):
        key = self.by_code.get(user_code)
        return dict(self.rows[key]) if key else None

    async def get_device_enrollment_by_secret_hash(self, *, secret_hash: str):
        row = self.rows.get(secret_hash)
        return dict(row) if row else None

    async def approve_device_enrollment(self, *, enrollment_id: str, user_id: str):
        for row in self.rows.values():
            if row["id"] == enrollment_id and row["state"] == "pending":
                row["state"] = "approved"
                row["user_id"] = user_id
                row["approved_at"] = datetime.now(timezone.utc).isoformat()
                return dict(row)
        return None

    async def consume_device_enrollment(
        self,
        *,
        secret_hash: str,
        token_hash: str,
        credential_expires_at: datetime,
    ):
        row = self.rows.get(secret_hash)
        if not row or row["state"] != "approved":
            return None
        row["state"] = "consumed"
        row["consumed_at"] = datetime.now(timezone.utc).isoformat()
        self.consumed.append(
            {
                "secret_hash": secret_hash,
                "token_hash": token_hash,
                "expires_at": credential_expires_at,
            }
        )
        return {
            "account_user_id": row["user_id"],
            "device_id": row["device_id"],
            "credential_id": "credential-1",
            "scopes": row["requested_scopes"],
        }

    async def has_recent_reauth(self, **_values) -> bool:
        return self.reauth


class DevicePairingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.store = FakePairingStore()
        self.service = DevicePairingService(
            self.store,
            enrollment_ttl=timedelta(minutes=10),
            credential_ttl=timedelta(days=90),
        )

    async def test_pairing_requires_browser_approval_before_token_delivery(self) -> None:
        started = await self.service.start(
            device_id="legion-y9000x",
            display_name="Legion Y9000X",
            capabilities=("agent.chat", "git.read"),
        )
        self.assertEqual(len(started.user_code), 8)
        self.assertTrue(started.pairing_secret.startswith("meo_pair_"))

        pending = await self.service.poll(pairing_secret=started.pairing_secret)
        self.assertEqual(pending.state, "pending")
        self.assertIsNone(pending.device_token)

        preview = await self.service.approve(
            identity=AccountIdentity("user-1", session_id="session-1"),
            user_code=started.user_code,
        )
        self.assertEqual(preview.display_name, "Legion Y9000X")

        approved = await self.service.poll(pairing_secret=started.pairing_secret)
        self.assertEqual(approved.state, "approved")
        assert approved.device_token is not None
        self.assertTrue(approved.device_token.startswith("meo_dev_"))
        self.assertEqual(
            self.store.consumed[0]["token_hash"],
            hashlib.sha256(approved.device_token.encode("utf-8")).hexdigest(),
        )

        second = await self.service.poll(pairing_secret=started.pairing_secret)
        self.assertEqual(second.state, "consumed")
        self.assertIsNone(second.device_token)

    async def test_approval_requires_same_session_recent_reauth(self) -> None:
        started = await self.service.start(
            device_id="legion-y9000x",
            display_name="Legion",
            capabilities=("agent.chat",),
        )
        self.store.reauth = False
        with self.assertRaises(PermissionError):
            await self.service.approve(
                identity=AccountIdentity("user-1", session_id="session-1"),
                user_code=started.user_code,
            )

    async def test_account_without_session_binding_cannot_approve(self) -> None:
        started = await self.service.start(
            device_id="legion-y9000x",
            display_name="Legion",
            capabilities=("agent.chat",),
        )
        with self.assertRaises(PermissionError):
            await self.service.approve(
                identity=AccountIdentity("user-1"),
                user_code=started.user_code,
            )

    async def test_device_cannot_request_credential_scopes(self) -> None:
        started = await self.service.start(
            device_id="legion-y9000x",
            display_name="Legion",
            capabilities=("agent.chat",),
        )
        secret_hash = hashlib.sha256(started.pairing_secret.encode("utf-8")).hexdigest()
        row = self.store.rows[secret_hash]
        self.assertEqual(row["requested_scopes"], ["relay.connect", "agent.run"])

    async def test_invalid_capability_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            await self.service.start(
                device_id="legion-y9000x",
                display_name="Legion",
                capabilities=("../../shell",),
            )


if __name__ == "__main__":
    unittest.main()
