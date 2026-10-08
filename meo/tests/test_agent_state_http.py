import json
import threading
import unittest
import urllib.request

from meo.runtime.http_transport import create_http_server
from meo.service.backend_adapter import ConversationMessage
from meo.service.core import AgentServiceCore


class FakeBackend:
    def list_conversations(self): return []
    def create_conversation(self): return "conversation:1"
    def conversation_exists(self, _conversation_id): return True
    def list_messages(self, _conversation_id): return [ConversationMessage("assistant", "hi")]
    def send_message(self, _conversation_id, _text, _callbacks): return object()
    def choose_tool_option(self, _execution_handle, _legacy_option_index): pass
    def cancel(self, _execution_handle): pass
    def list_models(self): return []
    def set_model(self, _conversation_id, _model_id): pass
    def list_skills(self): return []
    def set_skill_enabled(self, _skill_id, _enabled): pass
    def list_mcp_servers(self): return []


class AgentStateHttpTests(unittest.TestCase):
    def test_state_endpoint_reports_service_lifecycle(self):
        service = AgentServiceCore(FakeBackend())
        service.start_request("conversation:1")
        server = create_http_server(service, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(base + "/v1/agent-state", timeout=2) as response:
                self.assertEqual(response.status, 200)
                state = json.loads(response.read())
            self.assertTrue(state["ready"])
            self.assertEqual(state["active_requests"], 1)
            self.assertEqual(state["request_states"]["running_model"], 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
