from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from meo.cloud.enrollment import DeviceCredentialClaims, DeviceEnrollmentRequest


class EnrollmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)

    def test_device_enrollment_validates_identity_and_expiry(self) -> None:
        request = DeviceEnrollmentRequest.create(
            "enroll-1",
            "user-1",
            "legion",
            "Legion Y9000X",
            ["agent.chat", "agent.workspace"],
            self.now,
            self.now + timedelta(minutes=10),
        )
        self.assertEqual(request.device_id, "legion")
        self.assertEqual(request.capabilities, ("agent.chat", "agent.workspace"))

    def test_expired_enrollment_is_rejected(self) -> None:
        with self.assertRaises(PermissionError):
            DeviceEnrollmentRequest.create(
                "enroll-2",
                "user-1",
                "legion",
                "Legion",
                ["agent.chat"],
                self.now - timedelta(minutes=20),
                self.now - timedelta(minutes=10),
            )

    def test_device_credential_is_narrow_and_revocable(self) -> None:
        claims = DeviceCredentialClaims(
            credential_id="cred-1",
            account_user_id="user-1",
            device_id="legion",
            scopes=frozenset({"relay.connect", "agent.receive"}),
            issued_at=self.now,
            expires_at=self.now + timedelta(days=30),
        )
        self.assertTrue(claims.allows("relay.connect", now=self.now + timedelta(minutes=1)))
        self.assertFalse(claims.allows("provider.invoke", now=self.now + timedelta(minutes=1)))

        revoked = DeviceCredentialClaims(
            credential_id="cred-2",
            account_user_id="user-1",
            device_id="legion",
            scopes=frozenset({"relay.connect"}),
            issued_at=self.now - timedelta(days=1),
            expires_at=self.now + timedelta(days=30),
            revoked_at=self.now - timedelta(minutes=1),
        )
        self.assertFalse(revoked.allows("relay.connect", now=self.now))


if __name__ == "__main__":
    unittest.main()
