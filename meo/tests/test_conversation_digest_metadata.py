from __future__ import annotations

import unittest

from meo.service.response_meta import normalize_response_meta


class ConversationDigestMetadataTests(unittest.TestCase):
    def test_digest_and_activity_survive_response_normalization(self) -> None:
        normalized = normalize_response_meta({
            "type": "response_meta",
            "activity": {
                "title_summary": {"used": True, "status": "completed"},
            },
            "conversation_digest": {
                "status": "completed",
                "model_id": "cheap:tiny",
                "title": "Linux Build Fix",
                "summary": "The user asked for help fixing a Linux build.",
                "api_key_debug": "must-not-leak",
            },
        })

        self.assertTrue(normalized["activity"]["title_summary"]["used"])
        self.assertEqual(normalized["conversation_digest"]["title"], "Linux Build Fix")
        self.assertEqual(
            normalized["conversation_digest"]["summary"],
            "The user asked for help fixing a Linux build.",
        )
        self.assertEqual(normalized["conversation_digest"]["api_key_debug"], "<redacted>")
        self.assertNotIn("conversation_digest", normalized.get("extra", {}))


if __name__ == "__main__":
    unittest.main()
