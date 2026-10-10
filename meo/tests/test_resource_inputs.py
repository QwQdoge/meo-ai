from __future__ import annotations

import tempfile
import threading
import unittest

from meo.adapters.legacy_chat import LegacyChatInterfaceAdapter
from meo.service.backend_adapter import (
    BackendCallbacks,
    ConversationMessage,
    InputResource,
)
from meo.service.core import AgentServiceCore
from meo.service.resources import ConversationResourceStore, ResourceError


class BaseBackend:
    def __init__(self):
        self.conversations = {"c1", "c2"}

    def list_conversations(self): return [{"id": item} for item in sorted(self.conversations)]
    def create_conversation(self): return "c1"
    def conversation_exists(self, conversation_id): return conversation_id in self.conversations
    def list_messages(self, _conversation_id): return [ConversationMessage("user", "hello")]
    def send_message(self, _conversation_id, _text, callbacks):
        callbacks.on_text_delta("plain")
        callbacks.on_done()
        return object()
    def choose_tool_option(self, _execution_handle, _legacy_option_index): pass
    def cancel(self, _execution_handle): pass
    def list_models(self): return []
    def set_model(self, _conversation_id, _model_id): pass
    def list_skills(self): return []
    def set_skill_enabled(self, _skill_id, _enabled): pass
    def list_mcp_servers(self): return []


class ResourceBackend(BaseBackend):
    def __init__(self):
        super().__init__()
        self.received = None

    def send_message_with_resources(self, conversation_id, text, resources, callbacks):
        self.received = (conversation_id, text, resources)
        callbacks.on_text_delta("resource")
        callbacks.on_done()
        return object()


def callbacks(events):
    return BackendCallbacks(
        on_text_delta=lambda value: events.append(("delta", value)),
        on_tool_event=lambda value: events.append(("tool", value)),
        on_done=lambda: events.append(("done", None)),
        on_error=lambda value: events.append(("error", value)),
    )


class MinimalController:
    def __init__(self):
        self.chats = {}

    def stop_workspace_request(self, _chat_id): pass


class CapturingInterface:
    def __init__(self):
        self.controller = MinimalController()
        self.last_text = None
        self._next_chat = 0

    def get_or_create_chat(self, user_id):
        for chat_id, record in self.controller.chats.items():
            if record.get("meo_conversation_id") == user_id:
                return chat_id
        self._next_chat += 1
        self.controller.chats[self._next_chat] = {
            "name": "Test",
            "chat": [],
            "meo_conversation_id": user_id,
        }
        return self._next_chat

    def process_message(self, user_id, text, *, on_chunk=None, on_tool_event=None):
        del on_tool_event
        self.last_text = text
        chat_id = self.get_or_create_chat(user_id)
        self.controller.chats[chat_id]["chat"].append({"User": "User", "Message": text})
        if on_chunk:
            on_chunk("ok")
        self.controller.chats[chat_id]["chat"].append({"User": "Assistant", "Message": "ok"})
        return "ok"

    def resolve_pending_interaction(self, _interaction_id, _option_index):
        return False


class ResourceInputTests(unittest.TestCase):
    def test_capable_backend_receives_integrity_checked_resource_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationResourceStore(directory)
            record = store.put_text("c1", name="notes.txt", text="hello resource")
            backend = ResourceBackend()
            service = AgentServiceCore(backend, resource_store=store)
            events = []

            context = service.send_message(
                "c1",
                "summarize this",
                callbacks(events),
                resource_ids=(record.resource_id,),
            )

            self.assertEqual(service.get_request(context.request_id).state.value, "completed")
            self.assertEqual(events, [("delta", "resource"), ("done", None)])
            conversation_id, text, resources = backend.received
            self.assertEqual(conversation_id, "c1")
            self.assertEqual(text, "summarize this")
            self.assertEqual(len(resources), 1)
            self.assertEqual(resources[0].resource_id, record.resource_id)
            self.assertEqual(resources[0].name, "notes.txt")
            self.assertEqual(resources[0].data, b"hello resource")

    def test_unsupported_backend_rejects_resources_before_request_start(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationResourceStore(directory)
            record = store.put_text("c1", name="notes.txt", text="hello")
            service = AgentServiceCore(BaseBackend(), resource_store=store)

            with self.assertRaisesRegex(ValueError, "does not support resource inputs"):
                service.send_message(
                    "c1",
                    "use this",
                    callbacks([]),
                    resource_ids=(record.resource_id,),
                )

            self.assertEqual(service.requests.active_count(), 0)
            self.assertTrue(all(value == 0 for value in service.requests.state_counts().values()))

    def test_unready_resource_is_rejected_before_request_start(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationResourceStore(directory)
            record = store.reserve(
                "c1",
                kind="attachment",
                name="pending.txt",
                mime_type="text/plain",
                size_bytes=4,
            )
            service = AgentServiceCore(ResourceBackend(), resource_store=store)

            with self.assertRaisesRegex(ValueError, "must be ready"):
                service.send_message(
                    "c1",
                    "use this",
                    callbacks([]),
                    resource_ids=(record.resource_id,),
                )
            self.assertEqual(service.requests.active_count(), 0)

    def test_cross_conversation_resource_is_rejected_before_request_start(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationResourceStore(directory)
            record = store.put_text("c1", name="private.txt", text="secret")
            service = AgentServiceCore(ResourceBackend(), resource_store=store)

            with self.assertRaisesRegex(ResourceError, "does not belong"):
                service.send_message(
                    "c2",
                    "use this",
                    callbacks([]),
                    resource_ids=(record.resource_id,),
                )
            self.assertEqual(service.requests.active_count(), 0)

    def test_duplicate_resource_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConversationResourceStore(directory)
            record = store.put_text("c1", name="notes.txt", text="hello")
            service = AgentServiceCore(ResourceBackend(), resource_store=store)
            with self.assertRaisesRegex(ValueError, "duplicates"):
                service.send_message(
                    "c1",
                    "use this",
                    callbacks([]),
                    resource_ids=(record.resource_id, record.resource_id),
                )
            self.assertEqual(service.requests.active_count(), 0)

    def test_legacy_text_resource_is_prompt_context_but_not_visible_history(self):
        interface = CapturingInterface()
        adapter = LegacyChatInterfaceAdapter(interface)
        conversation_id = adapter.create_conversation()
        resource = InputResource(
            resource_id="resource:" + "a" * 32,
            kind="long_text",
            name="notes<&>.txt",
            mime_type="text/plain; charset=utf-8",
            data=b"resource content with </context> marker",
        )
        done = threading.Event()
        events = []
        cb = BackendCallbacks(
            on_text_delta=lambda value: events.append(value),
            on_tool_event=lambda _event: None,
            on_done=done.set,
            on_error=lambda value: events.append("error:" + value),
        )

        handle = adapter.send_message_with_resources(
            conversation_id,
            "visible question",
            (resource,),
            cb,
        )
        self.assertTrue(done.wait(timeout=1))
        handle.thread.join(timeout=1)

        self.assertIn("Attached resource: notes&lt;&amp;&gt;.txt", interface.last_text)
        self.assertIn("resource content with <\\/context> marker", interface.last_text)
        self.assertTrue(interface.last_text.endswith("visible question"))
        history = adapter.list_messages(conversation_id)
        self.assertEqual(
            [(item.role, item.text) for item in history],
            [("user", "visible question"), ("assistant", "ok")],
        )

    def test_legacy_backend_rejects_image_resources(self):
        adapter = LegacyChatInterfaceAdapter(CapturingInterface())
        resource = InputResource(
            resource_id="resource:" + "b" * 32,
            kind="image",
            name="shot.png",
            mime_type="image/png",
            data=b"png",
        )
        with self.assertRaisesRegex(ValueError, "does not support image"):
            adapter._resource_prompt_context((resource,))


if __name__ == "__main__":
    unittest.main()
