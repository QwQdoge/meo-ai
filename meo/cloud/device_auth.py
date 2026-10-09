from __future__ import annotations

import hashlib
from datetime import datetime

from meo.cloud.enrollment import DeviceCredentialClaims
from meo.cloud.store import CloudStore


class DeviceBearerVerifier:
    """Verify a narrow device bearer token using only its SHA-256 digest at rest."""

    def __init__(self, store: CloudStore) -> None:
        self.store = store

    async def verify(self, bearer_token: str) -> DeviceCredentialClaims:
        token = bearer_token.strip()
        if not token:
            raise PermissionError("device bearer credential is required")
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        row = await self.store.get_device_credential_by_hash(token_hash=digest)
        if row is None:
            raise PermissionError("invalid device credential")

        try:
            claims = DeviceCredentialClaims(
                credential_id=self._required_text(row, "id"),
                account_user_id=self._required_text(row, "user_id"),
                device_id=self._required_text(row, "device_id"),
                scopes=frozenset(self._string_list(row.get("scopes"), "scopes")),
                issued_at=self._timestamp(row.get("issued_at"), "issued_at"),
                expires_at=self._timestamp(row.get("expires_at"), "expires_at"),
                revoked_at=(
                    self._timestamp(row.get("revoked_at"), "revoked_at")
                    if row.get("revoked_at") is not None
                    else None
                ),
            )
            claims.validate()
        except (ValueError, PermissionError) as exc:
            raise PermissionError("invalid or expired device credential") from exc
        return claims

    @staticmethod
    def _required_text(row: dict, key: str) -> str:
        value = row.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"device credential {key} is invalid")
        return value.strip()

    @staticmethod
    def _string_list(value, key: str) -> tuple[str, ...]:
        if not isinstance(value, list) or not value:
            raise ValueError(f"device credential {key} is invalid")
        result = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
        if len(result) != len(value):
            raise ValueError(f"device credential {key} is invalid")
        return result

    @staticmethod
    def _timestamp(value, key: str) -> datetime:
        if not isinstance(value, str):
            raise ValueError(f"device credential {key} is invalid")
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            raise ValueError(f"device credential {key} must be timezone-aware")
        return parsed
