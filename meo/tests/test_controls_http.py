from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request

from meo.runtime.http_transport import create_http_server
from meo.service.backend_adapter import ConversationMessage
from meo.service.controls import AiControl, ControlOption, find_control
from meo.service.core import AgentServiceCore


class ControlBackendFake:
    def __init__(self):
        self.search_mode = "auto"
        self.memory = True

    def list_conversations(self): return [{"id": "c1"}]
    def create_conversation(self): return "c1"
    def conversation_exists(self, conversation_id): return conversation_id == "c1"
    def list_messages(self, _conversation_id): return [ConversationMessage("user", "hello")]
    def send_message(self, _conversation_id, _text, callbacks): callbacks.on_done(); return object()
    def choose_tool_option(self, _handle, _index): pass
    def cancel(self, _handle): pass
    def list_models(self): return []
    def set_model(self, _conversation_id, _model_id): pass
    def list_skills(self): return []
    def set_skill_enabled(self, _skill_id, _enabled): pass
    def list_mcp_servers(self): return []

    def list_controls(self):
        return [
            AiControl(
                "search.mode",
                "Search",
                "select",
                self.search_mode,
                options=(
                    ControlOption("auto", "Auto"),
                    ControlOption("on", "On"),
                    ControlOption("off", "Off"),
                ),
            ),
            AiControl("memory.enabled", "Memory", "toggle", self.memory),
        ]

    def set_control(self, control_id, value):
        control = find_control(self.list_controls(), control_id)
        value = control.validate_value(value)
        if control_id == "search.mode": self.search_mode = value
        elif control_id == "memory.enabled": self.memory = value
        return find_control(self.list_controls(), control_id)


class ControlHttpTests(unittest.TestCase):
    def setUp(self):
        self.backend = ControlBackendFake()
        self.server = create_http_server(AgentServiceCore(self.backend), port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    def request(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"} if data is not None else {}
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read())

    def test_lists_and_mutates_only_typed_controls(self):
        status, body = self.request("GET", "/v1/controls")
        self.assertEqual(status, 200)
        self.assertEqual(body["controls"][0]["control_id"], "search.mode")
        self.assertEqual(body["controls"][1]["value"], True)

        status, updated = self.request("POST", "/v1/controls/search.mode", {"value": "off"})
        self.assertEqual(status, 200)
        self.assertTrue(updated["accepted"])
        self.assertEqual(updated["control"]["value"], "off")
        self.assertEqual(self.backend.search_mode, "off")

    def test_invalid_control_value_fails_closed(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request("POST", "/v1/controls/search.mode", {"value": "unsupported"})
        self.assertEqual(raised.exception.code, 400)
        self.assertEqual(self.backend.search_mode, "auto")

    def test_backend_without_controls_returns_empty_catalog_and_rejects_write(self):
        class NoControls(ControlBackendFake):
            list_controls = None
            set_control = None

        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
        self.server = create_http_server(AgentServiceCore(NoControls()), port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

        _, body = self.request("GET", "/v1/controls")
        self.assertEqual(body["controls"], [])
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request("POST", "/v1/controls/memory.enabled", {"value": False})
        self.assertEqual(raised.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
