from __future__ import annotations

import hashlib
import re
import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from meo.cloud.account_auth import AccountIdentity
from meo.cloud.store import CloudStore, CloudStoreConflict


_DEVICE_ID = re.compile(r"^[A-Za-z0-9._:-]{3,128}$")
_CAPABILITY = re.compile(r"^[a-z][a-z0-9._-]{1,63}$")
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_DEFAULT_SCOPES = ("relay.connect", "agent.run")


@dataclass(frozen=True)
class PairingStart:
    enrollment_id: str
    user_code: str
    pairing_secret: str
    expires_at: datetime


@dataclass(frozen=True)
class PairingPreview:
    enrollment_id: str
    user_code: str
    device_id: str
    display_name: str
    capabilities: tuple[str, ...]
    expires_at: datetime


@dataclass(frozen=True)
class PairingPoll:
    state: str
    device_token: str | None = None
    device_id: str | None = None
    expires_at: datetime | None = None


class DevicePairingService:
    """Short-lived device pairing with browser approval and one-time token delivery."""

    def __init__(
        self,
        store: CloudStore,
        *,
        enrollment_ttl: timedelta = timedelta(minutes=10),
        credential_ttl: timedelta = timedelta(days=90),
    ) -> None:
        self.store = store
        self.enrollment_ttl = enrollment_ttl
        self.credential_ttl = credential_ttl

    async def start(
        self,
        *,
        device_id: str,
        display_name: str,
        capabilities: Iterable[str],
    ) -> PairingStart:
        device_id = device_id.strip()
        display_name = display_name.strip()
        normalized_capabilities = tuple(dict.fromkeys(item.strip() for item in capabilities))
        self._validate_device(device_id, display_name, normalized_capabilities)

        now = datetime.now(timezone.utc)
        expires_at = now + self.enrollment_ttl
        pairing_secret = "meo_pair_" + secrets.token_urlsafe(32)
        secret_hash = self._sha256(pairing_secret)

        # user_code has a unique constraint. In the very unlikely event of a
        # collision, retry with a fresh public code but never reuse a secret.
        last_error: Exception | None = None
        for _attempt in range(5):
            enrollment_id = str(uuid.uuid4())
            user_code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
            try:
                await self.store.create_device_enrollment(
                    enrollment_id=enrollment_id,
                    secret_hash=secret_hash,
                    user_code=user_code,
                    device_id=device_id,
                    display_name=display_name,
                    capabilities=normalized_capabilities,
                    requested_scopes=_DEFAULT_SCOPES,
                    expires_at=expires_at,
                )
            except CloudStoreConflict as exc:
                last_error = exc
                continue
            return PairingStart(enrollment_id, user_code, pairing_secret, expires_at)
        raise RuntimeError("could not allocate a device pairing code") from last_error

    async def preview(self, *, user_code: str) -> PairingPreview:
        code = self._normalize_code(user_code)
        row = await self.store.get_device_enrollment_by_code(user_code=code)
        if row is None:
            raise LookupError("pairing code not found")
        if row.get("state") != "pending":
            raise PermissionError("pairing request is no longer pending")
        expires_at = self._timestamp(row.get("expires_at"), "expires_at")
        if expires_at <= datetime.now(timezone.utc):
            raise PermissionError("pairing code has expired")
        return PairingPreview(
            enrollment_id=self._required_text(row, "id"),
            user_code=code,
            device_id=self._required_text(row, "device_id"),
            display_name=self._required_text(row, "display_name"),
            capabilities=self._text_tuple(row.get("capabilities"), "capabilities"),
            expires_at=expires_at,
        )

    async def approve(
        self,
        *,
        identity: AccountIdentity,
        user_code: str,
    ) -> PairingPreview:
        if not identity.session_id:
            raise PermissionError("this account session cannot approve devices")
        if not await self.store.has_recent_reauth(
            user_id=identity.user_id,
            session_id=identity.session_id,
            purpose="account_security",
        ):
            raise PermissionError("recent Meo Account verification is required")

        preview = await self.preview(user_code=user_code)
        row = await self.store.approve_device_enrollment(
            enrollment_id=preview.enrollment_id,
            user_id=identity.user_id,
        )
        if row is None:
            raise PermissionError("pairing request changed or expired")
        return preview

    async def poll(self, *, pairing_secret: str) -> PairingPoll:
        secret = pairing_secret.strip()
        if not secret.startswith("meo_pair_") or len(secret) < 40:
            raise PermissionError("invalid pairing secret")
        secret_hash = self._sha256(secret)
        row = await self.store.get_device_enrollment_by_secret_hash(secret_hash=secret_hash)
        if row is None:
            raise PermissionError("pairing request not found")

        state = row.get("state")
        expires_at = self._timestamp(row.get("expires_at"), "expires_at")
        now = datetime.now(timezone.utc)
        if expires_at <= now and state in {"pending", "approved"}:
            return PairingPoll("expired")
        if state == "pending":
            return PairingPoll("pending")
        if state in {"rejected", "expired", "consumed"}:
            return PairingPoll(str(state))
        if state != "approved":
            raise RuntimeError("pairing request has an invalid state")

        device_token = "meo_dev_" + secrets.token_urlsafe(40)
        credential_expires_at = now + self.credential_ttl
        consumed = await self.store.consume_device_enrollment(
            secret_hash=secret_hash,
            token_hash=self._sha256(device_token),
            credential_expires_at=credential_expires_at,
        )
        if consumed is None:
            # Another poll may have consumed it. Never mint or replay a second
            # plaintext credential because the first token is intentionally
            # delivered exactly once.
            return PairingPoll("consumed")
        return PairingPoll(
            "approved",
            device_token=device_token,
            device_id=self._required_text(consumed, "device_id"),
            expires_at=credential_expires_at,
        )

    @staticmethod
    def _validate_device(
        device_id: str,
        display_name: str,
        capabilities: tuple[str, ...],
    ) -> None:
        if not _DEVICE_ID.fullmatch(device_id):
            raise ValueError("device_id is invalid")
        if not display_name or len(display_name) > 80 or any(ord(ch) < 32 for ch in display_name):
            raise ValueError("display_name is invalid")
        if not capabilities or len(capabilities) > 32:
            raise ValueError("capabilities are required")
        if any(not _CAPABILITY.fullmatch(item) for item in capabilities):
            raise ValueError("capability name is invalid")

    @staticmethod
    def _normalize_code(value: str) -> str:
        code = value.strip().upper().replace("-", "").replace(" ", "")
        if len(code) != 8 or any(ch not in _CODE_ALPHABET for ch in code):
            raise ValueError("pairing code is invalid")
        return code

    @staticmethod
    def _sha256(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _required_text(row: dict, key: str) -> str:
        value = row.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"pairing row is missing {key}")
        return value.strip()

    @staticmethod
    def _text_tuple(value, label: str) -> tuple[str, ...]:
        if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
            raise RuntimeError(f"pairing row has invalid {label}")
        return tuple(value)

    @staticmethod
    def _timestamp(value, label: str) -> datetime:
        if not isinstance(value, str):
            raise RuntimeError(f"pairing row is missing {label}")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise RuntimeError(f"pairing row has invalid {label}") from exc
        if parsed.tzinfo is None:
            raise RuntimeError(f"pairing row has naive {label}")
        return parsed
