from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class AccountIdentity:
    user_id: str
    email: str | None = None
    session_id: str | None = None


@dataclass(frozen=True)
class MeoAccountAuthConfig:
    account_url: str

    def validate(self) -> None:
        if not self.account_url.startswith("https://"):
            raise ValueError("Meo Account URL must use https://")
        if self.account_url.rstrip("/") != self.account_url:
            raise ValueError("Meo Account URL must not end with a slash")


class MeoAccountTokenVerifier:
    """Verify a Meo Account OAuth access token through its userinfo endpoint.

    The user identity comes from the Meo Account OAuth resource server.
    Browser-supplied IDs are never accepted as identity.
    """

    def __init__(
        self,
        config: MeoAccountAuthConfig,
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
        user_id = result.get("sub", result.get("id"))
        if not isinstance(user_id, str) or not user_id.strip():
            raise PermissionError("account token has no valid subject")
        email = result.get("email")
        return AccountIdentity(
            user_id=user_id.strip(),
            email=email if isinstance(email, str) else None,
            session_id=self._session_id(token),
        )

    @staticmethod
    def _session_id(token: str) -> str | None:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        try:
            payload = parts[1]
            padded = payload + "=" * (-len(payload) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
            claims = json.loads(decoded.decode("utf-8"))
        except Exception:
            return None
        if not isinstance(claims, dict):
            return None
        session_id = claims.get("sid")
        return session_id.strip() if isinstance(session_id, str) and session_id.strip() else None

    def _request_user_sync(self, token: str) -> dict:
        request = Request(
            self.config.account_url.rstrip("/") + "/v1/auth/oauth2/userinfo",
            method="GET",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                raw = response.read()
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise PermissionError("invalid or expired account token") from exc
            raise RuntimeError(f"Meo Account userinfo request failed with HTTP {exc.code}") from exc
        try:
            value = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError("Meo Account returned invalid userinfo JSON") from exc
        if not isinstance(value, dict):
            raise RuntimeError("Meo Account returned invalid userinfo data")
        return value
