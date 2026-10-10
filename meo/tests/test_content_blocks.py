from __future__ import annotations

import unittest

from meo.service.content_blocks import (
    ContentBlockError,
    legacy_text_block,
    normalize_content_block,
    normalize_content_blocks,
)


class ContentBlockTests(unittest.TestCase):
    def test_user_legacy_text_stays_plain(self):
        block = legacy_text_block(
            block_id="turn:1:text",
            role="user",
            text="# do not render me as a heading",
        )
        self.assertEqual(block["type"], "text")
        self.assertEqual(block["text"], "# do not render me as a heading")

    def test_assistant_legacy_text_is_markdown_capable(self):
        block = legacy_text_block(
            block_id="turn:2:text",
            role="assistant",
            text="```bash\necho ok\n```",
        )
        self.assertEqual(block["type"], "markdown")

    def test_code_block_keeps_only_safe_metadata(self):
        block = normalize_content_block({
            "block_id": "code:1",
            "type": "code",
            "text": "print('ok')",
            "language": "python",
            "filename": "main.py",
            "command": "rm -rf /",
            "qml": "ApplicationWindow {}",
            "actions": [{"run": "anything"}],
        })
        self.assertEqual(
            block,
            {
                "block_id": "code:1",
                "type": "code",
                "text": "print('ok')",
                "language": "python",
                "filename": "main.py",
            },
        )

    def test_artifact_uses_resource_identity_not_local_path(self):
        block = normalize_content_block({
            "block_id": "artifact:report",
            "type": "artifact",
            "resource_id": "resource:report-1",
            "name": "report.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 2048,
            "state": "ready",
            "path": "/home/user/private/report.pdf",
        })
        self.assertNotIn("path", block)
        self.assertEqual(block["resource_id"], "resource:report-1")
        self.assertEqual(block["name"], "report.pdf")

    def test_image_dimensions_are_bounded_to_positive_integers(self):
        with self.assertRaises(ContentBlockError):
            normalize_content_block({
                "block_id": "image:1",
                "type": "image",
                "resource_id": "resource:image-1",
                "name": "shot.png",
                "mime_type": "image/png",
                "width": -1,
                "height": 1080,
            })

    def test_tool_activity_has_closed_state_vocabulary(self):
        good = normalize_content_block({
            "block_id": "activity:block:1",
            "type": "tool_activity",
            "activity_id": "activity:1",
            "title": "Run native tests",
            "state": "running",
            "detail": "7 / 10 completed",
            "source": "builtin",
        })
        self.assertEqual(good["state"], "running")

        with self.assertRaises(ContentBlockError):
            normalize_content_block({
                "block_id": "activity:block:2",
                "type": "tool_activity",
                "activity_id": "activity:2",
                "title": "Do something",
                "state": "whatever-the-model-says",
            })

    def test_confirmation_carries_identity_but_no_generic_actions(self):
        block = normalize_content_block({
            "block_id": "confirm:1",
            "type": "confirmation",
            "decision_id": "decision:abc",
            "title": "Allow Bluetooth change?",
            "detail": "Bluetooth will be enabled.",
            "actions": ["approve-without-router"],
        })
        self.assertEqual(block["decision_id"], "decision:abc")
        self.assertNotIn("actions", block)

    def test_block_array_is_bounded(self):
        blocks = [
            {"block_id": f"text:{index}", "type": "text", "text": "x"}
            for index in range(129)
        ]
        with self.assertRaises(ContentBlockError):
            normalize_content_blocks(blocks)

    def test_unknown_type_is_rejected(self):
        with self.assertRaises(ContentBlockError):
            normalize_content_block({
                "block_id": "dynamic:1",
                "type": "arbitrary_qml",
                "text": "ApplicationWindow {}",
            })


if __name__ == "__main__":
    unittest.main()
