import json
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

from meo.runtime.http_transport import create_http_server
from meo.service.backend_adapter import ConversationMessage, McpServerInfo, ModelInfo, SkillInfo
from meo.service.core import AgentServiceCore
from meo.service.memory import MemoryRecord


class _Backend:
    def __init__(self):
        self.enabled = True
        self.items = {
            "memory:one": MemoryRecord(
                memory_id="memory:one",
                text="Use compact native UI.",
                scope="account",
                source="test",
                created_at="2026-10-10T00:00:00Z",
                updated_at="2026-10-10T00:00:00Z",
            )
        }

    def list_conversations(self):
        return []

    def create_conversation(self):
        return "c1"

    def conversation_exists(self, conversation_id):
        return conversation_id == "c1"

    def list_messages(self, conversation_id):
        return [ConversationMessage("user", "hello")]

    def send_message(self, conversation_id, text, callbacks):
        callbacks.on_done()
        return object()

    def choose_tool_option(self, execution_handle, legacy_option_index):
        pass

    def cancel(self, execution_handle):
        pass

    def list_models(self):
        return [ModelInfo("local:test", "Test", "Local", selected=True)]

    def set_model(self, conversation_id, model_id):
        pass

    def list_skills(self):
        return [SkillInfo("s", "S", True)]

    def set_skill_enabled(self, skill_id, enabled):
        pass

    def list_mcp_servers(self):
        return [McpServerInfo("m", "M", False)]

    def memory_supported(self):
        return True

    def memory_enabled(self):
        return self.enabled

    def set_memory_enabled(self, enabled):
        self.enabled = bool(enabled)
        return self.enabled

    def list_memories(self, *, scope=None, query=""):
        values = list(self.items.values())
        if scope:
            values = [item for item in values if item.scope == scope]
        if query:
            wanted = query.casefold()
            values = [item for item in values if wanted in item.text.casefold()]
        return values

    def create_memory(self, text, *, pinned=False):
        record = MemoryRecord(
            memory_id="memory:created",
            text=text,
            scope="account",
            source="user",
            created_at="2026-10-10T00:00:00Z",
            updated_at="2026-10-10T00:00:00Z",
            pinned=pinned,
        )
        self.items[record.memory_id] = record
        return record

    def update_memory(self, memory_id, *, text=None, pinned=None):
        current = self.items[memory_id]
        record = MemoryRecord(
            memory_id=current.memory_id,
            text=current.text if text is None else text,
            scope=current.scope,
            source=current.source,
            created_at=current.created_at,
            updated_at="2026-10-10T01:00:00Z",
            state=current.state,
            pinned=current.pinned if pinned is None else pinned,
            sync_state=current.sync_state,
        )
        self.items[memory_id] = record
        return record

    def delete_memory(self, memory_id):
        if memory_id not in self.items:
            raise ValueError("unknown memory_id")
        del self.items[memory_id]


class MemoryHttpTests(unittest.TestCase):
    def setUp(self):
        self.backend = _Backend()
        self.server = create_http_server(AgentServiceCore(self.backend), port=0)
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

    def test_state_list_and_search(self):
        status, payload = self.request("GET", "/v1/memory")
        self.assertEqual(status, 200)
        self.assertTrue(payload["supported"])
        self.assertTrue(payload["enabled"])
        self.assertEqual(len(payload["memories"]), 1)

        query = urllib.parse.urlencode({"scope": "account", "q": "compact"})
        status, payload = self.request("GET", "/v1/memory?" + query)
        self.assertEqual(status, 200)
        self.assertEqual(payload["scope"], "account")
        self.assertEqual(payload["query"], "compact")
        self.assertEqual(len(payload["memories"]), 1)
        self.assertEqual(payload["memories"][0]["memory_id"], "memory:one")

    def test_toggle_create_update_pin_and_delete(self):
        status, state = self.request("POST", "/v1/memory/settings", {"enabled": False})
        self.assertEqual(status, 200)
        self.assertTrue(state["accepted"])
        self.assertFalse(state["enabled"])

        status, created = self.request(
            "POST", "/v1/memory", {"text": "Remember native cards", "pinned": True}
        )
        self.assertEqual(status, 201)
        self.assertTrue(created["accepted"])
        self.assertEqual(created["memory"]["memory_id"], "memory:created")
        self.assertTrue(created["memory"]["pinned"])

        status, updated = self.request(
            "POST", "/v1/memory/memory%3Acreated", {"text": "Remember cards", "pinned": False}
        )
        self.assertEqual(status, 200)
        self.assertTrue(updated["accepted"])
        self.assertEqual(updated["memory"]["text"], "Remember cards")
        self.assertFalse(updated["memory"]["pinned"])

        status, deleted = self.request("DELETE", "/v1/memory/memory%3Acreated")
        self.assertEqual(status, 200)
        self.assertTrue(deleted["accepted"])
        self.assertTrue(deleted["deleted"])

    def test_rejects_unsupported_query_and_empty_updates(self):
        with self.assertRaises(urllib.error.HTTPError) as bad_query:
            self.request("GET", "/v1/memory?unknown=1")
        self.assertEqual(bad_query.exception.code, 400)

        with self.assertRaises(urllib.error.HTTPError) as empty_update:
            self.request("POST", "/v1/memory/memory%3Aone", {})
        self.assertEqual(empty_update.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
