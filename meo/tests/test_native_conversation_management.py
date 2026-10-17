import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

from meo.runtime.native_http_transport import create_native_http_server
from meo.service.core import AgentServiceCore
from meo.service.resources import ConversationResourceStore


class ManagementBackend:
    def __init__(self):
        self.conversations = {
            "meo:first": {"title": "First chat", "summary": "Planning notes", "message_count": 4},
            "meo:second": {"title": "Second chat", "summary": "Other work", "message_count": 2},
        }

    def list_conversations(self):
        return [
            {"id": conversation_id, **metadata}
            for conversation_id, metadata in sorted(self.conversations.items())
        ]

    def conversation_exists(self, conversation_id):
        return conversation_id in self.conversations

    def search_conversations(self, query):
        if "migration" in query.casefold():
            return [
                {
                    "id": "meo:first",
                    "excerpt": "…migration causes and consequences…",
                    "match_role": "user",
                    "match_count": 2,
                    "legacy_chat_id": 999,
                    "private": "must-not-leak",
                }
            ]
        return []

    def rename_conversation(self, conversation_id, title):
        if conversation_id not in self.conversations:
            raise ValueError("unknown conversation_id")
        self.conversations[conversation_id]["title"] = title

    def delete_conversation(self, conversation_id):
        if conversation_id not in self.conversations:
            raise ValueError("unknown conversation_id")
        del self.conversations[conversation_id]


class NativeConversationManagementTests(unittest.TestCase):
    def setUp(self):
        self.backend = ManagementBackend()
        self.resources = tempfile.TemporaryDirectory()
        self.store = ConversationResourceStore(self.resources.name)
        self.service = AgentServiceCore(self.backend, resource_store=self.store)
        self.server = create_native_http_server(self.service, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
        self.resources.cleanup()

    def json_request(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"} if method == "POST" else {}
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read())

    def test_search_returns_safe_catalog_metadata_and_message_excerpt(self):
        query = urllib.parse.urlencode({"q": "migration causes"})
        status, payload = self.json_request("GET", f"/v1/conversations/search?{query}")
        self.assertEqual(status, 200)
        self.assertEqual(payload["query"], "migration causes")
        self.assertEqual(len(payload["results"]), 1)
        result = payload["results"][0]
        self.assertEqual(result["id"], "meo:first")
        self.assertEqual(result["title"], "First chat")
        self.assertEqual(result["summary"], "Planning notes")
        self.assertEqual(result["message_count"], 4)
        self.assertEqual(result["match_role"], "user")
        self.assertEqual(result["match_count"], 2)
        self.assertIn("migration causes", result["excerpt"])
        self.assertNotIn("legacy_chat_id", result)
        self.assertNotIn("private", result)

    def test_search_rejects_oversized_query(self):
        query = urllib.parse.urlencode({"q": "x" * 241})
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.json_request("GET", f"/v1/conversations/search?{query}")
        self.assertEqual(raised.exception.code, 400)

    def test_rename_normalizes_title_and_updates_backend(self):
        encoded = urllib.parse.quote("meo:first", safe="")
        status, payload = self.json_request(
            "POST",
            f"/v1/conversations/{encoded}/title",
            {"title": "  Product   planning  "},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["accepted"])
        self.assertEqual(payload["title"], "Product planning")
        self.assertEqual(self.backend.conversations["meo:first"]["title"], "Product planning")

        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.json_request(
                "POST",
                f"/v1/conversations/{encoded}/title",
                {"title": "   "},
            )
        self.assertEqual(raised.exception.code, 400)

    def test_delete_removes_conversation_and_scoped_resources(self):
        record = self.store.put_text("meo:first", name="notes.txt", text="private context")
        self.assertEqual(len(self.store.list_resources("meo:first")), 1)

        encoded = urllib.parse.quote("meo:first", safe="")
        status, payload = self.json_request("DELETE", f"/v1/conversations/{encoded}")
        self.assertEqual(status, 200)
        self.assertTrue(payload["deleted"])
        self.assertNotIn("meo:first", self.backend.conversations)
        self.assertEqual(self.store.list_resources("meo:first"), [])
        with self.assertRaises(ValueError):
            self.store.get("meo:first", record.resource_id)

    def test_delete_rejects_conversation_with_active_request(self):
        self.service.start_request("meo:first")
        encoded = urllib.parse.quote("meo:first", safe="")
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.json_request("DELETE", f"/v1/conversations/{encoded}")
        self.assertEqual(raised.exception.code, 409)
        self.assertIn("meo:first", self.backend.conversations)

    def test_unknown_conversation_management_is_not_found(self):
        encoded = urllib.parse.quote("meo:missing", safe="")
        with self.assertRaises(urllib.error.HTTPError) as renamed:
            self.json_request(
                "POST",
                f"/v1/conversations/{encoded}/title",
                {"title": "Missing"},
            )
        self.assertEqual(renamed.exception.code, 404)

        with self.assertRaises(urllib.error.HTTPError) as deleted:
            self.json_request("DELETE", f"/v1/conversations/{encoded}")
        self.assertEqual(deleted.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
