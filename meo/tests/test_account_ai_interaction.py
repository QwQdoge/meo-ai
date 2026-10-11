from __future__ import annotations

import unittest

from meo.system.account_ai import PreparedAccountInference
from meo.system.account_ai_interaction import (
    AccountAiConsentInteraction,
    AccountAiConsentUnavailable,
    bind_account_ai_consent_sink,
    request_account_ai_consent,
)


class AccountAiInteractionTest(unittest.TestCase):
    @staticmethod
    def prepared() -> PreparedAccountInference:
        return PreparedAccountInference(
            arguments={
                "connectionId": "connection-one",
                "model": "model-one",
                "purpose": "meo_ai_conversation",
                "systemPrompt": "private system prompt",
                "userPrompt": "private user prompt",
                "dataCategories": ["user_prompt", "conversation_history"],
                "temperature": 0.3,
                "maxOutputTokens": 2048,
            },
            consent={
                "requestId": "consent-one",
                "payloadSha256": "a" * 64,
                "confirmationVersion": 1,
                "provider": "openai_compatible",
                "providerName": "Example Provider",
                "model": "model-one",
                "purpose": "meo_ai_conversation",
                "dataCategories": ["user_prompt", "conversation_history"],
                "promptCharacters": 42,
            },
            request_id="request-one",
        )

    def test_public_event_contains_decision_metadata_but_not_prompt_text(self):
        interaction = AccountAiConsentInteraction(self.prepared())
        event = interaction.public_event()

        self.assertEqual(event["type"], "tool_interaction")
        self.assertEqual(event["tool_name"], "Meo Account AI")
        self.assertEqual([item["title"] for item in event["options"]], ["Allow once", "Deny"])
        self.assertIn("Example Provider", event["display_text"])
        self.assertIn("model-one", event["display_text"])
        self.assertIn("42 prompt characters", event["display_text"])
        self.assertNotIn("private user prompt", str(event))
        self.assertNotIn("private system prompt", str(event))
        self.assertNotIn("payloadSha256", str(event))

    def test_allow_and_deny_are_one_shot(self):
        allowed = AccountAiConsentInteraction(self.prepared())
        self.assertTrue(allowed.resolve(0))
        self.assertTrue(allowed.wait(timeout=0.1))
        self.assertFalse(allowed.resolve(1))

        denied = AccountAiConsentInteraction(self.prepared())
        self.assertTrue(denied.resolve(1))
        self.assertFalse(denied.wait(timeout=0.1))
        self.assertFalse(denied.resolve(0))

    def test_invalid_option_is_rejected(self):
        interaction = AccountAiConsentInteraction(self.prepared())
        with self.assertRaises(ValueError):
            interaction.resolve(2)

    def test_request_requires_bound_agent_interaction_sink(self):
        with self.assertRaisesRegex(AccountAiConsentUnavailable, "interactive"):
            request_account_ai_consent(self.prepared())

    def test_bound_sink_receives_exact_interaction(self):
        captured = []
        with bind_account_ai_consent_sink(captured.append):
            interaction = request_account_ai_consent(self.prepared())
        self.assertEqual(captured, [interaction])
        self.assertEqual(interaction.prepared.request_id, "request-one")

    def test_timeout_fails_closed(self):
        interaction = AccountAiConsentInteraction(self.prepared())
        with self.assertRaisesRegex(AccountAiConsentUnavailable, "timed out"):
            interaction.wait(timeout=0.001)


if __name__ == "__main__":
    unittest.main()
