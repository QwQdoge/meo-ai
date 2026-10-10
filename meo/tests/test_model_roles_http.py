import json
import threading
import unittest
import urllib.error
import urllib.request

from meo.runtime.http_transport import create_http_server
from meo.service.backend_adapter import ConversationMessage, McpServerInfo, ModelInfo, SkillInfo
from meo.service.core import AgentServiceCore
from meo.service.model_roles import ModelRoleRegistry


class _Backend:
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
        return [
            ModelInfo("cheap:tiny", "Tiny", "Cheap"),
            ModelInfo("main:strong", "Strong", "Main", selected=True),
        ]

    def set_model(self, conversation_id, model_id):
        pass

    def list_skills(self):
        return [SkillInfo("s", "S", True)]

    def set_skill_enabled(self, skill_id, enabled):
        pass

    def list_mcp_servers(self):
        return [McpServerInfo("m", "M", False)]


class ModelRoleHttpTests(unittest.TestCase):
    def setUp(self):
        service = AgentServiceCore(_Backend(), model_roles=ModelRoleRegistry())
        self.server = create_http_server(service, port=0)
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

    def test_lists_and_updates_non_secret_role_preferences(self):
        status, payload = self.request("GET", "/v1/model-roles")
        self.assertEqual(status, 200)
        roles = payload["model_roles"]
        self.assertEqual([item["role_id"] for item in roles], ["title", "judge", "reasoning", "execution"])
        self.assertTrue(all(item["runtime_supported"] is False for item in roles))

        status, updated = self.request(
            "POST", "/v1/model-roles/title", {"model_id": "cheap:tiny"}
        )
        self.assertEqual(status, 200)
        self.assertTrue(updated["accepted"])
        self.assertEqual(updated["role"]["preferred_model_id"], "cheap:tiny")

        _, refreshed = self.request("GET", "/v1/model-roles")
        title = next(item for item in refreshed["model_roles"] if item["role_id"] == "title")
        self.assertEqual(title["preferred_model_id"], "cheap:tiny")

    def test_rejects_unknown_model_and_role(self):
        with self.assertRaises(urllib.error.HTTPError) as missing_model:
            self.request("POST", "/v1/model-roles/judge", {"model_id": "missing:model"})
        self.assertEqual(missing_model.exception.code, 400)

        with self.assertRaises(urllib.error.HTTPError) as missing_role:
            self.request("POST", "/v1/model-roles/security", {"model_id": "main:strong"})
        self.assertEqual(missing_role.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
