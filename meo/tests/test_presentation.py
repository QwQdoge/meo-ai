import unittest

from meo.service.backend_adapter import BackendCallbacks, ConversationMessage, McpServerInfo, ModelInfo, SkillInfo
from meo.service.core import AgentServiceCore
from meo.service.presentation import normalize_presentation_card


class PresentationContractTests(unittest.TestCase):
    def test_normalizes_bounded_native_card(self):
        event = normalize_presentation_card(
            {
                "type": "presentation_card",
                "card": {
                    "card_id": "weather:today",
                    "kind": "metric",
                    "title": "Today",
                    "subtitle": "Singapore",
                    "value": "31 °C",
                    "detail": "Partly cloudy",
                },
            }
        )
        self.assertEqual(event["type"], "presentation.card")
        self.assertEqual(event["card"]["kind"], "metric")
        self.assertEqual(event["card"]["value"], "31 °C")

    def test_rejects_arbitrary_ui_kind_and_oversized_text(self):
        with self.assertRaisesRegex(ValueError, "unsupported presentation card kind"):
            normalize_presentation_card(
                {"type": "presentation_card", "card": {"kind": "qml", "title": "Run this"}}
            )
        with self.assertRaisesRegex(ValueError, "too long"):
            normalize_presentation_card(
                {"type": "presentation_card", "card": {"kind": "info", "title": "x" * 121}}
            )

    def test_drops_unregistered_action_or_code_fields(self):
        event = normalize_presentation_card(
            {
                "type": "presentation_card",
                "card": {
                    "kind": "system",
                    "title": "Bluetooth",
                    "value": "On",
                    "action": {"command": "rm -rf /"},
                    "qml": "import QtQuick; Item {}",
                    "url": "file:///etc/passwd",
                },
            }
        )
        self.assertNotIn("action", event["card"])
        self.assertNotIn("qml", event["card"])
        self.assertNotIn("url", event["card"])


class _CardBackend:
    def __init__(self):
        self.conversation = "c1"

    def list_conversations(self):
        return [{"id": self.conversation}]

    def create_conversation(self):
        return self.conversation

    def conversation_exists(self, conversation_id):
        return conversation_id == self.conversation

    def list_messages(self, conversation_id):
        return [ConversationMessage("user", "hello")]

    def send_message(self, conversation_id, text, callbacks):
        callbacks.on_tool_event(
            {
                "type": "presentation_card",
                "card": {"kind": "status", "title": "Build", "value": "Passing"},
            }
        )
        callbacks.on_done()
        return object()

    def choose_tool_option(self, execution_handle, legacy_option_index):
        raise AssertionError("no tool decision expected")

    def cancel(self, execution_handle):
        pass

    def list_models(self):
        return [ModelInfo("local:tiny", "Tiny", "Local", selected=True)]

    def set_model(self, conversation_id, model_id):
        pass

    def list_skills(self):
        return [SkillInfo("s", "S", True)]

    def set_skill_enabled(self, skill_id, enabled):
        pass

    def list_mcp_servers(self):
        return [McpServerInfo("m", "M", False)]


class PresentationCoreTests(unittest.TestCase):
    def test_backend_card_is_normalized_with_request_context(self):
        service = AgentServiceCore(_CardBackend())
        events = []
        callbacks = BackendCallbacks(
            on_text_delta=lambda _text: None,
            on_tool_event=events.append,
            on_done=lambda: None,
            on_error=lambda error: self.fail(error),
        )
        context = service.send_message("c1", "show status", callbacks)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "presentation.card")
        self.assertEqual(events[0]["request_id"], context.request_id)
        self.assertEqual(events[0]["conversation_id"], "c1")
        self.assertEqual(events[0]["card"]["title"], "Build")


if __name__ == "__main__":
    unittest.main()
