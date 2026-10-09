from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import FrozenSet


class ChatGrantMode(str, Enum):
    ASK_EVERY_TIME = "ask_every_time"
    SESSION = "session"
    PERSISTENT = "persistent"


_ALLOWED_DATA_CATEGORIES = frozenset(
    {
        "chat_text",
        "system_instructions",
        "conversation_context",
        "attachment_text",
        "image_input",
    }
)


@dataclass(frozen=True)
class ChatGrant:
    """A revocable permission to use one Account-owned AI credential for chat.

    This object never contains the provider API key. The credential identifier is
    meaningful only to the Meo Account provider broker.
    """

    grant_id: str
    user_id: str
    client_id: str
    credential_id: str
    mode: ChatGrantMode
    data_categories: FrozenSet[str]
    issued_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None

    def validate(self, *, now: datetime | None = None) -> None:
        current = now or datetime.now(timezone.utc)
        if self.issued_at.tzinfo is None:
            raise ValueError("issued_at must be timezone-aware")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        if self.revoked_at is not None and self.revoked_at.tzinfo is None:
            raise ValueError("revoked_at must be timezone-aware")
        if not self.grant_id or not self.user_id or not self.client_id or not self.credential_id:
            raise ValueError("grant identity fields are required")
        if not self.data_categories:
            raise ValueError("at least one data category is required")
        unknown = self.data_categories - _ALLOWED_DATA_CATEGORIES
        if unknown:
            raise ValueError(f"unsupported data categories: {sorted(unknown)}")
        if self.expires_at is not None and self.expires_at <= self.issued_at:
            raise ValueError("grant expiry must be after issuance")
        if self.mode is ChatGrantMode.SESSION and self.expires_at is None:
            raise ValueError("session grants require an expiry")
        if self.mode is ChatGrantMode.ASK_EVERY_TIME:
            raise ValueError("ask_every_time does not create a reusable chat grant")
        if self.revoked_at is not None and self.revoked_at < self.issued_at:
            raise ValueError("revocation cannot predate issuance")
        if self.revoked_at is not None and self.revoked_at <= current:
            raise PermissionError("chat grant has been revoked")
        if self.expires_at is not None and self.expires_at <= current:
            raise PermissionError("chat grant has expired")

    def allows(self, requested_categories: set[str], *, now: datetime | None = None) -> bool:
        try:
            self.validate(now=now)
        except (ValueError, PermissionError):
            return False
        return requested_categories.issubset(self.data_categories)


@dataclass(frozen=True)
class BrokerInferenceRequest:
    """Meo AI -> Account broker request metadata for normal chat inference."""

    grant_id: str
    credential_id: str
    client_id: str
    model: str
    purpose: str
    data_categories: FrozenSet[str]
    system_prompt: str
    user_prompt: str

    def validate(self) -> None:
        if not self.grant_id or not self.credential_id or not self.client_id:
            raise ValueError("grant, credential and client identity are required")
        if not self.model.strip() or len(self.model) > 160:
            raise ValueError("model is invalid")
        if not self.purpose.strip() or len(self.purpose) > 240:
            raise ValueError("purpose is invalid")
        if not self.user_prompt.strip():
            raise ValueError("user prompt is required")
        if len(self.system_prompt) + len(self.user_prompt) > 48000:
            raise ValueError("AI input is too large")
        unknown = self.data_categories - _ALLOWED_DATA_CATEGORIES
        if unknown or not self.data_categories:
            raise ValueError("data categories are invalid")
