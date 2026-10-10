from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from meo.cloud.contracts import BrokerInferenceRequest, ChatGrant, ChatGrantMode


class ChatGrantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 9, 11, 30, tzinfo=timezone.utc)

    def test_session_grant_allows_subset_of_categories(self) -> None:
        grant = ChatGrant(
            grant_id="grant-1",
            user_id="user-1",
            client_id="meo-ai-web",
            credential_id="credential-1",
            mode=ChatGrantMode.SESSION,
            data_categories=frozenset({"chat_text", "conversation_context"}),
            issued_at=self.now,
            expires_at=self.now + timedelta(hours=8),
        )
        self.assertTrue(grant.allows({"chat_text"}, now=self.now + timedelta(minutes=1)))
        self.assertFalse(grant.allows({"attachment_text"}, now=self.now + timedelta(minutes=1)))

    def test_expired_or_revoked_grant_is_rejected(self) -> None:
        expired = ChatGrant(
            grant_id="grant-2",
            user_id="user-1",
            client_id="meo-ai-web",
            credential_id="credential-1",
            mode=ChatGrantMode.SESSION,
            data_categories=frozenset({"chat_text"}),
            issued_at=self.now - timedelta(hours=2),
            expires_at=self.now - timedelta(hours=1),
        )
        self.assertFalse(expired.allows({"chat_text"}, now=self.now))

        revoked = ChatGrant(
            grant_id="grant-3",
            user_id="user-1",
            client_id="meo-ai-web",
            credential_id="credential-1",
            mode=ChatGrantMode.PERSISTENT,
            data_categories=frozenset({"chat_text"}),
            issued_at=self.now - timedelta(hours=2),
            revoked_at=self.now - timedelta(minutes=1),
        )
        self.assertFalse(revoked.allows({"chat_text"}, now=self.now))

    def test_ask_every_time_is_not_reusable(self) -> None:
        grant = ChatGrant(
            grant_id="grant-4",
            user_id="user-1",
            client_id="meo-ai-web",
            credential_id="credential-1",
            mode=ChatGrantMode.ASK_EVERY_TIME,
            data_categories=frozenset({"chat_text"}),
            issued_at=self.now,
        )
        with self.assertRaises(ValueError):
            grant.validate(now=self.now)

    def test_naive_current_time_is_rejected_cleanly(self) -> None:
        grant = ChatGrant(
            grant_id="grant-5",
            user_id="user-1",
            client_id="meo-ai-web",
            credential_id="credential-1",
            mode=ChatGrantMode.SESSION,
            data_categories=frozenset({"chat_text"}),
            issued_at=self.now,
            expires_at=self.now + timedelta(hours=1),
        )
        with self.assertRaisesRegex(ValueError, "now must be timezone-aware"):
            grant.validate(now=datetime(2026, 10, 9, 11, 31))


class BrokerInferenceRequestTests(unittest.TestCase):
    def test_valid_request_contains_no_provider_secret(self) -> None:
        request = BrokerInferenceRequest(
            grant_id="grant-1",
            credential_id="credential-1",
            client_id="meo-ai-web",
            model="example-model",
            purpose="interactive_chat",
            data_categories=frozenset({"chat_text", "conversation_context"}),
            system_prompt="You are Meo AI.",
            user_prompt="Hello",
        )
        request.validate()
        self.assertFalse(hasattr(request, "api_key"))

    def test_unknown_data_category_is_rejected(self) -> None:
        request = BrokerInferenceRequest(
            grant_id="grant-1",
            credential_id="credential-1",
            client_id="meo-ai-web",
            model="example-model",
            purpose="interactive_chat",
            data_categories=frozenset({"passwords"}),
            system_prompt="",
            user_prompt="Hello",
        )
        with self.assertRaises(ValueError):
            request.validate()


if __name__ == "__main__":
    unittest.main()
