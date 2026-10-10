import json
import threading
import unittest
import urllib.parse
import urllib.request

from meo.runtime.native_http_transport import create_native_http_server
from meo.service.core import AgentServiceCore
from meo.service.memory import MemoryRecord


class _MemoryBackend:
    def __init__(self):
        self.enabled = True
        self.items = {
            "memory:one": MemoryRecord(
                memory_id="memory:one",
                text="Use compact native UI.",
                scope="account",
                source="test",
                created_at="2026-10-10T00:00:00Z",
            )
        }

    def memory_supported(self):
        return True

    def memory_enabled(self):
        return self.enabled

    def set_memory_enabled(self, enabled):
        self.enabled = bool(enabled)
        return self.enabled

    def list_memories(self, *, scope=None, query=""):
        records = list(self.items.values())
        if scope:
            records = [item for item in records if item.scope == scope]
        if query:
            wanted = query.casefold()
            records = [item for item in records if wanted in item.text.casefold()]
        return records

    def create_memory(self, text, *, pinned=False):
        item = MemoryRecord(
            memory_id="memory:created",
            text=text,
            scope="account",
            source="user",
            created_at="2026-10-10T00:00:00Z",
            pinned=pinned,
        )
        self.items[item.memory_id] = item
        return item

    def update_memory(self, memory_id, *, text=None, pinned=None):
        current = self.items[memory_id]
        item = MemoryRecord(
            memory_id=current.memory_id,
            text=current.text if text is None else text,
            scope=current.scope,
            source=current.source,
            created_at=current.created_at,
            updated_at="2026-10-10T01:00:00Z",
            pinned=current.pinned if pinned is None else pinned,
        )
        self.items[memory_id] = item
        return item

    def delete_memory(self, memory_id):
        del self.items[memory_id]


class NativeHttpTransportTests(unittest.TestCase):
    def setUp(self):
        self.backend = _MemoryBackend()
        self.server = create_native_http_server(AgentServiceCore(self.backend), port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    def request(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"} if method == "POST" else {}
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read())

    def test_native_get_combines_state_search_and_records(self):
        query = urllib.parse.urlencode({"scope": "account", "q": "compact"})
        status, payload = self.request("GET", "/v1/memory?" + query)
        self.assertEqual(status, 200)
        self.assertTrue(payload["supported"])
        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["scope"], "account")
        self.assertEqual(payload["query"], "compact")
        self.assertEqual(payload["memories"][0]["memory_id"], "memory:one")

    def test_native_mutation_aliases_map_to_canonical_api(self):
        status, state = self.request("POST", "/v1/memory/settings", {"enabled": False})
        self.assertEqual(status, 200)
        self.assertFalse(state["enabled"])

        status, created = self.request(
            "POST", "/v1/memory", {"text": "Remember native cards", "pinned": True}
        )
        self.assertEqual(status, 201)
        self.assertTrue(created["memory"]["pinned"])

        status, updated = self.request(
            "POST", "/v1/memory/memory%3Acreated", {"text": "Remember cards", "pinned": False}
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["memory"]["text"], "Remember cards")
        self.assertFalse(updated["memory"]["pinned"])

        status, deleted = self.request("DELETE", "/v1/memory/memory%3Acreated")
        self.assertEqual(status, 200)
        self.assertTrue(deleted["deleted"])


if __name__ == "__main__":
    unittest.main()
