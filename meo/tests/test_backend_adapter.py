import unittest

from meo.service.backend_adapter import (
    AgentBackendAdapter,
    BackendCallbacks,
    McpServerInfo,
    ModelInfo,
    SkillInfo,
)


class FakeBackend:
    def list_conversations(self):
        return [{"id": "c1", "title": "Test"}]

    def create_conversation(self):
        return "c2"

    def conversation_exists(self, conversation_id):
        return conversation_id in {"c1", "c2"}

    def send_message(self, conversation_id, text, callbacks):
        callbacks.on_text_delta("hi")
        callbacks.on_done()
        return {"conversation_id": conversation_id, "text": text}

    def choose_tool_option(self, execution_handle, legacy_option_index):
        execution_handle["choice"] = legacy_option_index

    def cancel(self, execution_handle):
        execution_handle["cancelled"] = True

    def list_models(self):
        return [ModelInfo("m1", "Model 1", "local")]

    def set_model(self, conversation_id, model_id):
        self.model = (conversation_id, model_id)

    def list_skills(self):
        return [SkillInfo("s1", "Skill 1", True)]

    def set_skill_enabled(self, skill_id, enabled):
        self.skill = (skill_id, enabled)

    def list_mcp_servers(self):
        return [McpServerInfo("x1", "MCP 1", False)]


class BackendAdapterContractTests(unittest.TestCase):
    def test_structural_protocol_accepts_fake_backend(self):
        backend = FakeBackend()
        self.assertIsInstance(backend, AgentBackendAdapter)

    def test_callbacks_are_transport_independent(self):
        events = []
        callbacks = BackendCallbacks(
            on_text_delta=lambda text: events.append(("delta", text)),
            on_tool_event=lambda event: events.append(("tool", event)),
            on_done=lambda: events.append(("done", None)),
            on_error=lambda error: events.append(("error", error)),
        )
        FakeBackend().send_message("c1", "hello", callbacks)
        self.assertEqual(events, [("delta", "hi"), ("done", None)])

    def test_metadata_types_are_small_and_ui_free(self):
        self.assertEqual(ModelInfo("m", "M").model_id, "m")
        self.assertTrue(SkillInfo("s", "S", True).enabled)
        self.assertFalse(McpServerInfo("x", "X", False).enabled)


if __name__ == "__main__":
    unittest.main()
