from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable


class EnrollmentState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass(frozen=True)
class DeviceEnrollmentRequest:
    enrollment_id: str
    account_user_id: str
    device_id: str
    display_name: str
    capabilities: tuple[str, ...]
    created_at: datetime
    expires_at: datetime

    @classmethod
    def create(
        cls,
        enrollment_id: str,
        account_user_id: str,
        device_id: str,
        display_name: str,
        capabilities: Iterable[str],
        created_at: datetime,
        expires_at: datetime,
    ) -> "DeviceEnrollmentRequest":
        request = cls(
            enrollment_id=str(enrollment_id).strip(),
            account_user_id=str(account_user_id).strip(),
            device_id=str(device_id).strip(),
            display_name=str(display_name).strip(),
            capabilities=tuple(str(item).strip() for item in capabilities),
            created_at=created_at,
            expires_at=expires_at,
        )
        request.validate()
        return request

    def validate(self, *, now: datetime | None = None) -> None:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        for value, label in (
            (self.enrollment_id, "enrollment_id"),
            (self.account_user_id, "account_user_id"),
            (self.device_id, "device_id"),
            (self.display_name, "display_name"),
        ):
            if not value:
                raise ValueError(f"{label} is required")
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("enrollment timestamps must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("enrollment expiry must be after creation")
        if self.expires_at <= current:
            raise PermissionError("device enrollment has expired")
        if not self.capabilities:
            raise ValueError("at least one capability is required")
        if any(not item for item in self.capabilities):
            raise ValueError("capabilities must be non-empty")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("capabilities must be unique")


@dataclass(frozen=True)
class DeviceCredentialClaims:
    credential_id: str
    account_user_id: str
    device_id: str
    scopes: frozenset[str]
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def validate(self, *, now: datetime | None = None) -> None:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        if not self.credential_id or not self.account_user_id or not self.device_id:
            raise ValueError("device credential identity is incomplete")
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("device credential timestamps must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValueError("device credential expiry must be after issuance")
        if self.revoked_at is not None and self.revoked_at.tzinfo is None:
            raise ValueError("revoked_at must be timezone-aware")
        if self.revoked_at is not None and self.revoked_at <= current:
            raise PermissionError("device credential is revoked")
        if self.expires_at <= current:
            raise PermissionError("device credential has expired")
        if not self.scopes:
            raise ValueError("device credential requires scopes")

    def allows(self, scope: str, *, now: datetime | None = None) -> bool:
        try:
            self.validate(now=now)
        except (ValueError, PermissionError):
            return False
        return scope in self.scopes
