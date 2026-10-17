import unittest

from meo.adapters.conversation_catalog import PublicConversationCatalogBridge


class FakeBackend:
    def __init__(self):
        self.renamed = None

    def list_conversations(self):
        return [
            {
                "id": "meo:old",
                "legacy_chat_id": 4,
                "title": "Older",
                "summary": "Old summary",
                "message_count": 2,
                "internal_secret": "do-not-publish",
            },
            {
                "id": "meo:new",
                "legacy_chat_id": 11,
                "title": "Newest",
                "summary": "New summary",
                "title_is_default": False,
                "message_count": 8,
            },
            {"id": "not-meo", "legacy_chat_id": 99, "title": "Ignore"},
            {"legacy_chat_id": 12, "title": "Missing ID"},
        ]

    def rename_conversation(self, conversation_id, title):
        self.renamed = (conversation_id, title)


class PublicConversationCatalogBridgeTests(unittest.TestCase):
    def test_catalog_is_safe_and_recent_first(self):
        backend = FakeBackend()
        bridge = PublicConversationCatalogBridge(backend)

        catalog = bridge.list_conversations()

        self.assertEqual([item["id"] for item in catalog], ["meo:new", "meo:old"])
        self.assertEqual(catalog[0]["title"], "Newest")
        self.assertEqual(catalog[0]["message_count"], 8)
        self.assertFalse(catalog[0]["title_is_default"])
        self.assertEqual(catalog[1]["summary"], "Old summary")
        for item in catalog:
            self.assertNotIn("legacy_chat_id", item)
            self.assertNotIn("internal_secret", item)

    def test_non_catalog_capabilities_delegate_to_wrapped_backend(self):
        backend = FakeBackend()
        bridge = PublicConversationCatalogBridge(backend)
        bridge.rename_conversation("meo:new", "Renamed")
        self.assertEqual(backend.renamed, ("meo:new", "Renamed"))


if __name__ == "__main__":
    unittest.main()
