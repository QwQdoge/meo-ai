import threading
import unittest

from meo.adapters.legacy_chat import LegacyChatInterfaceAdapter
from meo.service.backend_adapter import BackendCallbacks


class FakeController:
    def __init__(self):
        self.cancelled = []

    def stop_workspace_request(self, chat_id):
        self.cancelled.append(chat_id)


class FakeInterface:
    def __init__(self):
        self.controller = FakeController()
        self._next_chat = 10
        self.pending = {}
        self.release = threading.Event()

    def get_or_create_chat(self, user_id):
        self._next_chat += 1
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
        self.pending["legacy-1"] = None
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

    def test_unknown_conversation_is_rejected(self):
        adapter = LegacyChatInterfaceAdapter(FakeInterface())
        with self.assertRaises(ValueError):
            adapter.send_message("meo:missing", "hello", self.callbacks([], threading.Event()))

    def test_attach_requires_meo_session_key(self):
        adapter = LegacyChatInterfaceAdapter(FakeInterface())
        with self.assertRaises(ValueError):
            adapter.attach_existing_session("not-meo")


if __name__ == "__main__":
    unittest.main()
