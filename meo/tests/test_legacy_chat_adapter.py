import threading
import unittest

from meo.adapters.legacy_chat import LegacyChatInterfaceAdapter
from meo.service.backend_adapter import BackendCallbacks


class FakeSettings:
    def get_string(self, key):
        if key == "language-model":
            return "fake"
        if key == "llm-settings":
            return "{}"
        return ""


class FakeController:
    def __init__(self):
        self.cancelled = []
        self.chats = {}
        self.saved = 0
        self.settings = FakeSettings()

    def workspace_chats(self):
        return self.chats

    def save_chats(self):
        self.saved += 1

    def stop_workspace_request(self, chat_id):
        self.cancelled.append(chat_id)


class FakePendingResult:
    def __init__(self, release):
        self.release = release
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        self.release.set()


class FakeInterface:
    def __init__(self, controller=None):
        self.controller = controller or FakeController()
        self._next_chat = max(self.controller.chats, default=10)
        self.pending = {}
        self._pending_interactions = self.pending
        self.release = threading.Event()
        self.last_pending_result = None

    def get_or_create_chat(self, user_id):
        for chat_id, record in self.controller.chats.items():
            if record.get("meo_conversation_id") == user_id:
                return chat_id
        self._next_chat += 1
        self.controller.chats[self._next_chat] = {"name": f"Chat {self._next_chat}", "chat": []}
        return self._next_chat

    def process_message(self, user_id, text, *, on_chunk=None, on_tool_event=None):
        if on_chunk:
            on_chunk("hello")
        event = {
            "type": "tool_interaction",
            "tool_name": "terminal",
            "interaction_id": "legacy-1",
            "options": [{"index": 0, "title": "Deny"}, {"index": 1, "title": "Approve"}],
        }
        self.last_pending_result = FakePendingResult(self.release)
        self.pending["legacy-1"] = {"result": self.last_pending_result}
        if on_tool_event:
            on_tool_event(event)
        self.release.wait(timeout=2)
        return "hello"

    def resolve_pending_interaction(self, interaction_id, option_index):
        if interaction_id not in self.pending:
            return False
        self.pending.pop(interaction_id)
        self.release.set()
        return True


class LegacyChatInterfaceAdapterTests(unittest.TestCase):
    def callbacks(self, events, tool_ready):
        return BackendCallbacks(
            on_text_delta=lambda text: events.append(("delta", text)),
            on_tool_event=lambda event: (events.append(("tool", event)), tool_ready.set()),
            on_done=lambda: events.append(("done", None)),
            on_error=lambda error: events.append(("error", error)),
        )

    def test_create_send_tool_choice_and_cancel(self):
        interface = FakeInterface()
        adapter = LegacyChatInterfaceAdapter(interface)
        conversation_id = adapter.create_conversation()
        self.assertTrue(adapter.conversation_exists(conversation_id))
        self.assertEqual(
            interface.controller.chats[adapter._conversations[conversation_id]]["meo_conversation_id"],
            conversation_id,
        )
        events = []
        tool_ready = threading.Event()
        handle = adapter.send_message(conversation_id, "hello", self.callbacks(events, tool_ready))
        self.assertTrue(tool_ready.wait(timeout=1))
        self.assertEqual(handle.pending_interaction_id, "legacy-1")
        adapter.choose_tool_option(handle, 1)
        handle.thread.join(timeout=1)
        self.assertIn(("delta", "hello"), events)
        self.assertEqual(events[-1], ("done", None))
        adapter.cancel(handle)
        self.assertEqual(interface.controller.cancelled, [handle.chat_id])

    def test_cancel_releases_pending_interaction_worker(self):
        interface = FakeInterface()
        adapter = LegacyChatInterfaceAdapter(interface)
        conversation_id = adapter.create_conversation()
        events = []
        tool_ready = threading.Event()
        handle = adapter.send_message(conversation_id, "hello", self.callbacks(events, tool_ready))
        self.assertTrue(tool_ready.wait(timeout=1))
        self.assertTrue(handle.thread.is_alive())

        adapter.cancel(handle)
        handle.thread.join(timeout=1)

        self.assertFalse(handle.thread.is_alive())
        self.assertIsNone(handle.pending_interaction_id)
        self.assertEqual(interface.pending, {})
        self.assertTrue(interface.last_pending_result.cancelled)
        self.assertEqual(interface.controller.cancelled, [handle.chat_id])
        self.assertEqual(events[-1], ("done", None))

    def test_history_only_exposes_visible_user_and_assistant_text(self):
        controller = FakeController()
        controller.chats = {
            11: {
                "name": "History",
                "meo_conversation_id": "meo:history",
                "chat": [
                    {"User": "User", "Message": "<context>private retrieval context</context>\n\nHello"},
                    {"User": "Console", "Message": "secret tool output"},
                    {"User": "Command", "Message": "/tool something"},
                    {"User": "Assistant", "Message": "Hi there"},
                    {"User": "File", "Message": "/tmp/private.txt"},
                    {"User": "Assistant", "Message": 123},
                ],
            }
        }
        adapter = LegacyChatInterfaceAdapter(FakeInterface(controller))
        history = adapter.list_messages("meo:history")
        self.assertEqual(
            [(item.role, item.text) for item in history],
            [("user", "Hello"), ("assistant", "Hi there")],
        )

    def test_conversation_mapping_survives_adapter_recreation(self):
        controller = FakeController()
        first = LegacyChatInterfaceAdapter(FakeInterface(controller))
        conversation_id = first.create_conversation()
        chat_id = first._conversations[conversation_id]

        second = LegacyChatInterfaceAdapter(FakeInterface(controller))
        self.assertTrue(second.conversation_exists(conversation_id))
        self.assertEqual(second._conversations[conversation_id], chat_id)
        listed = second.list_conversations()
        self.assertEqual(listed[0]["id"], conversation_id)
        self.assertEqual(listed[0]["legacy_chat_id"], chat_id)

    def test_duplicate_conversation_metadata_is_not_guessed(self):
        controller = FakeController()
        controller.chats = {
            11: {"name": "A", "meo_conversation_id": "meo:duplicate"},
            12: {"name": "B", "meo_conversation_id": "meo:duplicate"},
        }
        adapter = LegacyChatInterfaceAdapter(FakeInterface(controller))
        self.assertFalse(adapter.conversation_exists("meo:duplicate"))
        self.assertNotIn("meo:duplicate", {item["id"] for item in adapter.list_conversations()})
        with self.assertRaises(ValueError):
            adapter.attach_existing_session("meo:duplicate")

    def test_unknown_conversation_is_rejected(self):
        adapter = LegacyChatInterfaceAdapter(FakeInterface())
        with self.assertRaises(ValueError):
            adapter.send_message("meo:missing", "hello", self.callbacks([], threading.Event()))
        with self.assertRaises(ValueError):
            adapter.list_messages("meo:missing")

    def test_attach_requires_meo_session_key(self):
        adapter = LegacyChatInterfaceAdapter(FakeInterface())
        with self.assertRaises(ValueError):
            adapter.attach_existing_session("not-meo")


if __name__ == "__main__":
    unittest.main()
