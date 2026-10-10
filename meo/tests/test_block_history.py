from __future__ import annotations

import unittest

from meo.service.backend_adapter import ConversationMessage
from meo.service.core import AgentServiceCore


class HistoryBackend:
    def conversation_exists(self, conversation_id):
        return conversation_id == "c1"

    def list_messages(self, conversation_id):
        return [
            ConversationMessage("user", "# pasted heading"),
            ConversationMessage("assistant", "## Answer\n\n```python\nprint('ok')\n```"),
        ]


class BlockHistoryTests(unittest.TestCase):
    def test_history_keeps_legacy_text_and_adds_blocks(self):
        messages = AgentServiceCore(HistoryBackend()).list_messages("c1")

        self.assertEqual(messages[0]["text"], "# pasted heading")
        self.assertEqual(messages[0]["blocks"][0]["type"], "text")
        self.assertEqual(messages[0]["blocks"][0]["text"], "# pasted heading")

        self.assertEqual(messages[1]["text"], "## Answer\n\n```python\nprint('ok')\n```")
        self.assertEqual(messages[1]["blocks"][0]["type"], "markdown")
        self.assertEqual(messages[1]["blocks"][0]["block_id"], "history:1:text")

    def test_unknown_conversation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown conversation_id"):
            AgentServiceCore(HistoryBackend()).list_messages("missing")


if __name__ == "__main__":
    unittest.main()
