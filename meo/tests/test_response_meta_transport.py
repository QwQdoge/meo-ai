from __future__ import annotations

import unittest

from meo.runtime.http_transport import AgentHttpTransport
from meo.service.backend_adapter import BackendCallbacks, ConversationMessage, McpServerInfo, ModelInfo, SkillInfo
from meo.service.core import AgentServiceCore


class MetaBackend:
    def list_conversations(self):
        return [{"id": "conversation:1"}]

    def create_conversation(self):
        return "conversation:1"

    def conversation_exists(self, conversation_id):
        return conversation_id == "conversation:1"

    def list_messages(self, conversation_id):
        return [ConversationMessage("user", "hello")]

    def send_message(self, conversation_id, text, callbacks: BackendCallbacks):
        callbacks.on_text_delta("done")
        callbacks.on_tool_event({
            "type": "response_meta",
            "provider": "example",
            "model": "example-model",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 25,
                "completion_tokens_details": {"reasoning_tokens": 7},
            },
            "timing": {"total_ms": 650, "first_token_ms": 80},
            "context": {"window_tokens": 1000, "used_tokens": 250},
            "activity": {
                "memory": {"used": True},
                "search": {"queries": ["query"]},
            },
            "provider_metadata": {
                "reasoning_summary": "provider-visible summary",
                "headers": {"Authorization": "Bearer private"},
                "future": {"kept": True},
            },
        })
        callbacks.on_done()
        return {"ok": True}

    def choose_tool_option(self, execution_handle, legacy_option_index):
        raise AssertionError("not used")

    def cancel(self, execution_handle):
        return None

    def list_models(self):
        return [ModelInfo("example:model", "Example", "example", selected=True)]

    def set_model(self, conversation_id, model_id):
        return None

    def list_skills(self):
        return [SkillInfo("skill", "Skill", True)]

    def set_skill_enabled(self, skill_id, enabled):
        return None

    def list_mcp_servers(self):
        return [McpServerInfo("mcp", "MCP", True)]


class ResponseMetaTransportTests(unittest.TestCase):
    def test_response_metadata_survives_service_and_event_journal(self):
        transport = AgentHttpTransport(AgentServiceCore(MetaBackend()))
        request_id, _journal = transport.send_message("conversation:1", "hello")
        events = list(transport.stream_events(request_id))
        meta = next(event for event in events if event["type"] == "response.meta")

        self.assertEqual(meta["provider"], "example")
        self.assertEqual(meta["model"], "example-model")
        self.assertEqual(meta["usage"]["input_tokens"], 100)
        self.assertEqual(meta["usage"]["output_tokens"], 25)
        self.assertEqual(meta["usage"]["reasoning_tokens"], 7)
        self.assertEqual(meta["context"]["percent_used"], 25.0)
        self.assertTrue(meta["activity"]["memory"]["used"])
        self.assertTrue(meta["reasoning"]["available"])
        self.assertEqual(meta["provider_metadata"]["future"], {"kept": True})
        self.assertEqual(meta["provider_metadata"]["headers"]["Authorization"], "<redacted>")
        self.assertEqual(events[-1]["type"], "request.completed")


if __name__ == "__main__":
    unittest.main()
