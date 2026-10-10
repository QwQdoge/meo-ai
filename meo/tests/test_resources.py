from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from meo.service.resources import ConversationResourceStore, ResourceError


class ResourceStoreTests(unittest.TestCase):
    def test_text_resource_persists_without_exposing_backing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationResourceStore(directory)
            record = store.put_text(
                "conversation:1",
                name="pasted-text.txt",
                text="你好\nhello",
            )

            public = record.public_dict()
            self.assertEqual(public["kind"], "long_text")
            self.assertEqual(public["name"], "pasted-text.txt")
            self.assertEqual(public["mime_type"], "text/plain; charset=utf-8")
            self.assertNotIn("conversation_id", public)
            self.assertNotIn("path", public)
            self.assertEqual(store.read_bytes("conversation:1", record.resource_id), "你好\nhello".encode("utf-8"))

            reloaded = ConversationResourceStore(directory)
            restored = reloaded.get("conversation:1", record.resource_id)
            self.assertEqual(restored.sha256, record.sha256)
            self.assertEqual(restored.size_bytes, len("你好\nhello".encode("utf-8")))

    def test_binary_upload_is_reserved_then_finalized(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationResourceStore(directory)
            reserved = store.reserve(
                "conversation:1",
                kind="image",
                name="截图.png",
                mime_type="image/png",
                size_bytes=8,
            )
            self.assertEqual(reserved.state, "uploading")
            self.assertEqual(reserved.sha256, "")
            with self.assertRaisesRegex(ResourceError, "not ready"):
                store.read_bytes("conversation:1", reserved.resource_id)

            ready = store.finalize_upload(
                "conversation:1",
                reserved.resource_id,
                b"png-data",
            )
            self.assertEqual(ready.state, "ready")
            self.assertEqual(len(ready.sha256), 64)
            self.assertEqual(
                store.read_bytes("conversation:1", ready.resource_id),
                b"png-data",
            )

    def test_binary_upload_must_match_reserved_size(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationResourceStore(directory)
            reserved = store.reserve(
                "conversation:1",
                kind="attachment",
                name="notes.txt",
                mime_type="text/plain",
                size_bytes=5,
            )
            with self.assertRaisesRegex(ResourceError, "reserved size"):
                store.finalize_upload("conversation:1", reserved.resource_id, b"four")
            self.assertEqual(store.get("conversation:1", reserved.resource_id).state, "uploading")

    def test_ready_resource_cannot_be_uploaded_again(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationResourceStore(directory)
            record = store.put_bytes(
                "conversation:1",
                kind="attachment",
                name="notes.txt",
                mime_type="text/plain",
                data=b"hello",
            )
            with self.assertRaisesRegex(ResourceError, "not awaiting upload"):
                store.finalize_upload("conversation:1", record.resource_id, b"hello")

    def test_resource_identity_is_conversation_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationResourceStore(directory)
            record = store.put_bytes(
                "conversation:a",
                kind="attachment",
                name="notes.md",
                mime_type="text/markdown",
                data=b"hello",
            )
            with self.assertRaisesRegex(ResourceError, "does not belong"):
                store.get("conversation:b", record.resource_id)
            with self.assertRaisesRegex(ResourceError, "does not belong"):
                store.read_bytes("conversation:b", record.resource_id)

    def test_name_cannot_smuggle_a_path(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationResourceStore(directory)
            for name in ("../secret.txt", "folder/file.txt", "folder\\file.txt"):
                with self.subTest(name=name):
                    with self.assertRaisesRegex(ResourceError, "must not contain a path"):
                        store.put_bytes(
                            "conversation:1",
                            kind="attachment",
                            name=name,
                            mime_type="text/plain",
                            data=b"x",
                        )

    def test_resource_size_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationResourceStore(directory, max_resource_bytes=4)
            with self.assertRaisesRegex(ResourceError, "size limit"):
                store.put_bytes(
                    "conversation:1",
                    kind="attachment",
                    name="large.bin",
                    mime_type="application/octet-stream",
                    data=b"12345",
                )
            with self.assertRaisesRegex(ResourceError, "size limit"):
                store.reserve(
                    "conversation:1",
                    kind="attachment",
                    name="large.bin",
                    mime_type="application/octet-stream",
                    size_bytes=5,
                )

    def test_integrity_failure_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationResourceStore(directory)
            record = store.put_bytes(
                "conversation:1",
                kind="image",
                name="shot.png",
                mime_type="image/png",
                data=b"png-data",
            )
            token = record.resource_id.split(":", 1)[1]
            (Path(directory) / "objects" / token).write_bytes(b"tampered")
            with self.assertRaisesRegex(ResourceError, "integrity"):
                store.read_bytes("conversation:1", record.resource_id)

    def test_delete_removes_metadata_and_content(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationResourceStore(directory)
            record = store.put_text("conversation:1", name="paste.txt", text="hello")
            store.delete("conversation:1", record.resource_id)
            with self.assertRaisesRegex(ResourceError, "unknown resource_id"):
                store.get("conversation:1", record.resource_id)


if __name__ == "__main__":
    unittest.main()
