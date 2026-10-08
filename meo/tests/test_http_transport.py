import json
import threading
import unittest
import urllib.error
import urllib.request

from meo.runtime.http_transport import create_http_server
from meo.service.backend_adapter import BackendCallbacks, ConversationMessage, McpServerInfo, ModelInfo, SkillInfo
from meo.service.core import AgentServiceCore


class FakeHandle:
    def __init__(self):
        self.choice = threading.Event()
        self.cancel = threading.Event()
        self.choice_index = None


class FakeBackend:
    def __init__(self):
        self.conversations = set()
        self.handles = []
        self.model_changes = []
        self.skill_enabled = {"diagnostics": True}

    def list_conversations(self):
        return [{"id": cid} for cid in sorted(self.conversations)]

    def create_conversation(self):
        cid = f"conversation:{len(self.conversations) + 1}"
        self.conversations.add(cid)
        return cid

    def conversation_exists(self, conversation_id):
        return conversation_id in self.conversations

    def list_messages(self, conversation_id):
        if conversation_id not in self.conversations:
            raise ValueError("unknown conversation_id")
        return [
            ConversationMessage("user", "hello"),
            ConversationMessage("assistant", "Hi from history"),
        ]

    def send_message(self, conversation_id, text, callbacks: BackendCallbacks):
        handle = FakeHandle()
        self.handles.append(handle)

        def run():
            callbacks.on_text_delta("hello")
            callbacks.on_tool_event({
                "type": "tool_interaction",
                "tool_name": "terminal",
                "interaction_id": "legacy-1",
                "options": [
                    {"index": 0, "title": "Deny"},
                    {"index": 1, "title": "Approve"},
                ],
            })
            while not handle.choice.wait(0.01):
                if handle.cancel.is_set():
                    callbacks.on_done()
                    return
            callbacks.on_text_delta(f" choice={handle.choice_index}")
            callbacks.on_done()

        threading.Thread(target=run, daemon=True).start()
        return handle

    def choose_tool_option(self, execution_handle, legacy_option_index):
        execution_handle.choice_index = legacy_option_index
        execution_handle.choice.set()

    def cancel(self, execution_handle):
        execution_handle.cancel.set()

    def list_models(self):
        return [ModelInfo("local:tiny", "Tiny", "Local")]

    def set_model(self, conversation_id, model_id):
        self.model_changes.append((conversation_id, model_id))

    def list_skills(self):
        return [SkillInfo("diagnostics", "Diagnostics", self.skill_enabled["diagnostics"])]

    def set_skill_enabled(self, skill_id, enabled):
        if skill_id != "diagnostics":
            raise ValueError("unknown skill_id")
        self.skill_enabled[skill_id] = enabled

    def list_mcp_servers(self):
        return [McpServerInfo("filesystem", "Filesystem", False)]


class HttpTransportTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.server = create_http_server(AgentServiceCore(self.backend), port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    def json_request(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"} if method == "POST" else {}
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read())

    def read_event(self, response):
        while True:
            line = response.readline()
            if not line:
                return None
            if line.startswith(b"data: "):
                return json.loads(line[6:])

    def create_conversation(self):
        status, body = self.json_request("POST", "/v1/conversations")
        self.assertEqual(status, 201)
        return body["conversation_id"]

    def open_message_stream(self, conversation_id, text="test"):
        request = urllib.request.Request(
            self.base + f"/v1/conversations/{conversation_id}/messages",
            data=json.dumps({"text": text}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        response = urllib.request.urlopen(request, timeout=3)
        return response.headers["X-Meo-Request-Id"], response

    def test_conversation_history_is_structured_and_unknown_id_is_not_found(self):
        cid = self.create_conversation()
        status, history = self.json_request("GET", f"/v1/conversations/{cid}/messages")
        self.assertEqual(status, 200)
        self.assertEqual(history["conversation_id"], cid)
        self.assertEqual(
            history["messages"],
            [
                {"role": "user", "text": "hello"},
                {"role": "assistant", "text": "Hi from history"},
            ],
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.json_request("GET", "/v1/conversations/conversation:missing/messages")
        self.assertEqual(raised.exception.code, 404)

    def test_unknown_conversation_message_is_404_before_request_start(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.json_request(
                "POST",
                "/v1/conversations/conversation:missing/messages",
                {"text": "must not execute"},
            )
        self.assertEqual(raised.exception.code, 404)
        self.assertEqual(self.backend.handles, [])
        _, state = self.json_request("GET", "/v1/agent-state")
        self.assertEqual(state["active_requests"], 0)
        self.assertTrue(state["request_states"])
        self.assertTrue(all(count == 0 for count in state["request_states"].values()))

    def test_catalogs_and_mutations_are_structured(self):
        cid = self.create_conversation()
        status, models = self.json_request("GET", "/v1/models")
        self.assertEqual(status, 200)
        self.assertEqual(models["models"][0]["model_id"], "local:tiny")

        status, selected = self.json_request(
            "POST", f"/v1/conversations/{cid}/model", {"model_id": "local:tiny"}
        )
        self.assertEqual(status, 200)
        self.assertTrue(selected["accepted"])
        self.assertEqual(self.backend.model_changes, [(cid, "local:tiny")])

        _, skills = self.json_request("GET", "/v1/skills")
        self.assertTrue(skills["skills"][0]["enabled"])
        _, toggled = self.json_request("POST", "/v1/skills/diagnostics", {"enabled": False})
        self.assertFalse(toggled["enabled"])
        self.assertFalse(self.backend.skill_enabled["diagnostics"])

        _, mcp = self.json_request("GET", "/v1/mcp-servers")
        self.assertEqual(mcp["mcp_servers"][0]["server_id"], "filesystem")

    def test_message_tool_decision_and_completion(self):
        cid = self.create_conversation()
        request_id, response = self.open_message_stream(cid)
        events = []
        decision = None
        while True:
            event = self.read_event(response)
            if event is None:
                break
            events.append(event)
            self.assertGreaterEqual(event["seq"], 1)
            if event["type"] == "tool.requested":
                decision = event
                status, accepted = self.json_request(
                    "POST",
                    f"/v1/requests/{request_id}/decisions/{event['decision_id']}",
                    {"option_index": 1},
                )
                self.assertEqual(status, 200)
                self.assertTrue(accepted["accepted"])
        response.close()
        self.assertEqual(events[0]["type"], "request.started")
        self.assertEqual(events[0]["request_id"], request_id)
        self.assertTrue(any(event["type"] == "message.delta" for event in events))
        self.assertIsNotNone(decision)
        self.assertEqual(events[-1]["type"], "request.completed")
        self.assertEqual(self.backend.handles[0].choice_index, 1)

    def test_disconnect_then_reconnect_after_last_sequence(self):
        cid = self.create_conversation()
        request_id, response = self.open_message_stream(cid)
        tool_event = None
        while tool_event is None:
            event = self.read_event(response)
            self.assertIsNotNone(event)
            if event["type"] == "tool.requested":
                tool_event = event
        last_seq = tool_event["seq"]
        response.close()

        reconnect = urllib.request.urlopen(
            self.base + f"/v1/requests/{request_id}/events?after={last_seq}",
            timeout=3,
        )
        status, accepted = self.json_request(
            "POST",
            f"/v1/requests/{request_id}/decisions/{tool_event['decision_id']}",
            {"option_index": 1},
        )
        self.assertEqual(status, 200)
        self.assertTrue(accepted["accepted"])

        resumed = []
        while True:
            event = self.read_event(reconnect)
            if event is None:
                break
            resumed.append(event)
        reconnect.close()
        self.assertTrue(resumed)
        self.assertTrue(all(event["seq"] > last_seq for event in resumed))
        self.assertEqual(resumed[-1]["type"], "request.completed")
        self.assertTrue(any(event["type"] == "message.delta" for event in resumed))

        _, state = self.json_request("GET", f"/v1/requests/{request_id}")
        self.assertTrue(state["terminal"])
        self.assertGreaterEqual(state["event_journal"]["latest_seq"], resumed[-1]["seq"])

    def test_cancel_request_uses_request_id_not_stream_disconnect(self):
        cid = self.create_conversation()
        request_id, response = self.open_message_stream(cid)
        saw_tool = False
        while True:
            event = self.read_event(response)
            if event is None:
                break
            if event["type"] == "tool.requested":
                saw_tool = True
                status, cancelled = self.json_request("POST", f"/v1/requests/{request_id}/cancel")
                self.assertEqual(status, 200)
                self.assertTrue(cancelled["accepted"])
            if event["type"] == "request.cancelled":
                break
        response.close()
        self.assertTrue(saw_tool)
        self.assertTrue(self.backend.handles[0].cancel.is_set())
        _, state = self.json_request("GET", f"/v1/requests/{request_id}")
        self.assertEqual(state["state"], "cancelled")

    def test_browser_origin_is_rejected(self):
        request = urllib.request.Request(
            self.base + "/v1/models",
            method="GET",
            headers={"Origin": "https://evil.example"},
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 403)

    def test_non_json_post_is_rejected(self):
        request = urllib.request.Request(
            self.base + "/v1/conversations",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "text/plain"},
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 415)

    def test_non_loopback_bind_is_rejected(self):
        with self.assertRaises(ValueError):
            create_http_server(AgentServiceCore(FakeBackend()), host="0.0.0.0", port=0)


if __name__ == "__main__":
    unittest.main()
