from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class AccountIdentity:
    user_id: str
    email: str | None = None


@dataclass(frozen=True)
class SupabaseAccountAuthConfig:
    project_url: str
    publishable_key: str

    def validate(self) -> None:
        if not self.project_url.startswith("https://"):
            raise ValueError("Supabase project URL must use https://")
        if not self.publishable_key.strip():
            raise ValueError("Supabase publishable key is required")


class SupabaseAccountTokenVerifier:
    """Verify a Meo Account access token without trusting browser-supplied IDs."""

    def __init__(
        self,
        config: SupabaseAccountAuthConfig,
        *,
        request_user: Callable[[str], Any] | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self._request_user_override = request_user

    async def verify(self, bearer_token: str) -> AccountIdentity:
        token = bearer_token.strip()
        if not token:
            raise PermissionError("account bearer token is required")
        if self._request_user_override is not None:
            result = self._request_user_override(token)
            if asyncio.iscoroutine(result):
                result = await result
        else:
            result = await asyncio.to_thread(self._request_user_sync, token)
        if not isinstance(result, dict):
            raise PermissionError("invalid account identity response")
        user_id = result.get("id")
        if not isinstance(user_id, str) or not user_id.strip():
            raise PermissionError("account token has no valid subject")
        email = result.get("email")
        return AccountIdentity(
            user_id=user_id.strip(),
            email=email if isinstance(email, str) else None,
        )

    def _request_user_sync(self, token: str) -> dict:
        request = Request(
            self.config.project_url.rstrip("/") + "/auth/v1/user",
            method="GET",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": self.config.publishable_key,
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                raw = response.read()
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise PermissionError("invalid or expired account token") from exc
            raise RuntimeError(f"Supabase Auth request failed with HTTP {exc.code}") from exc
        try:
            value = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError("Supabase Auth returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise RuntimeError("Supabase Auth returned invalid user data")
        return value
