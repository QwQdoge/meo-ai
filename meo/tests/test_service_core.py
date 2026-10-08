import unittest

from meo.service.backend_adapter import BackendCallbacks
from meo.service.core import AgentServiceCore
from meo.service.request_state import RequestState


class FakeBackend:
    def __init__(self, *, complete_synchronously=False, tool_event=None):
        self.complete_synchronously = complete_synchronously
        self.tool_event = tool_event
        self.callbacks = None
        self.handle = {"cancelled": False, "choices": []}

    def list_conversations(self):
        return [{"id": "conversation:1"}]

    def create_conversation(self):
        return "conversation:1"

    def conversation_exists(self, conversation_id):
        return conversation_id == "conversation:1"

    def send_message(self, conversation_id, text, callbacks):
        self.callbacks = callbacks
        callbacks.on_text_delta("hello")
        if self.tool_event is not None:
            callbacks.on_tool_event(self.tool_event)
        if self.complete_synchronously:
            callbacks.on_done()
        return self.handle

    def choose_tool_option(self, execution_handle, legacy_option_index):
        execution_handle["choices"].append(legacy_option_index)

    def cancel(self, execution_handle):
        execution_handle["cancelled"] = True

    def list_models(self):
        return []

    def set_model(self, conversation_id, model_id):
        pass

    def list_skills(self):
        return []

    def set_skill_enabled(self, skill_id, enabled):
        pass

    def list_mcp_servers(self):
        return []


class AgentServiceCoreTests(unittest.TestCase):
    def event(self):
        return {
            "type": "tool_interaction",
            "tool_name": "terminal",
            "interaction_id": "legacy-tool-1",
            "options": [
                {"index": 0, "title": "Deny"},
                {"index": 1, "title": "Approve"},
            ],
        }

    def callbacks(self, events):
        return BackendCallbacks(
            on_text_delta=lambda text: events.append(("delta", text)),
            on_tool_event=lambda event: events.append(("tool", event)),
            on_done=lambda: events.append(("done", None)),
            on_error=lambda error: events.append(("error", error)),
        )

    def test_request_context_and_tool_round_trip(self):
        service = AgentServiceCore()
        context = service.start_request("conversation:1")
        event = service.publish_legacy_tool_request(context.request_id, self.event())
        self.assertEqual(event["conversation_id"], "conversation:1")
        self.assertEqual(service.get_request(context.request_id).state, RequestState.AWAITING_TOOL)
        legacy_index = service.choose_tool_option(context.request_id, event["decision_id"], 1)
        self.assertEqual(legacy_index, 1)
        self.assertEqual(service.get_request(context.request_id).state, RequestState.RUNNING_TOOL)
        service.tool_completed(context.request_id)
        service.complete_request(context.request_id)
        self.assertEqual(service.get_request(context.request_id).state, RequestState.COMPLETED)

    def test_backend_send_and_cancel_use_same_execution_handle(self):
        backend = FakeBackend()
        service = AgentServiceCore(backend)
        events = []
        context = service.send_message("conversation:1", "hello", self.callbacks(events))
        self.assertEqual(events, [("delta", "hello")])
        self.assertTrue(service.cancel_request(context.request_id))
        self.assertTrue(backend.handle["cancelled"])
        backend.callbacks.on_done()
        self.assertEqual(service.get_request(context.request_id).state, RequestState.CANCELLED)
        self.assertEqual(events[-1], ("done", None))

    def test_backend_tool_choice_is_forwarded_only_after_service_decision(self):
        backend = FakeBackend()
        service = AgentServiceCore(backend)
        events = []
        context = service.send_message("conversation:1", "hello", self.callbacks(events))
        backend.callbacks.on_tool_event(self.event())
        normalized = events[-1][1]
        service.choose_tool_option(context.request_id, normalized["decision_id"], 1)
        self.assertEqual(backend.handle["choices"], [1])

    def test_tool_callback_before_backend_returns_still_has_execution_handle(self):
        backend = FakeBackend(tool_event=self.event())
        service = AgentServiceCore(backend)
        events = []
        context = service.send_message("conversation:1", "hello", self.callbacks(events))
        normalized = next(payload for kind, payload in events if kind == "tool")
        self.assertEqual(service.get_request(context.request_id).state, RequestState.AWAITING_TOOL)
        service.choose_tool_option(context.request_id, normalized["decision_id"], 1)
        self.assertEqual(backend.handle["choices"], [1])

    def test_synchronous_backend_completion_does_not_leave_stale_handle(self):
        backend = FakeBackend(complete_synchronously=True)
        service = AgentServiceCore(backend)
        events = []
        context = service.send_message("conversation:1", "hello", self.callbacks(events))
        self.assertEqual(service.get_request(context.request_id).state, RequestState.COMPLETED)
        self.assertFalse(service.cancel_request(context.request_id))
        self.assertEqual(events[-1], ("done", None))

    def test_decision_cannot_cross_requests(self):
        service = AgentServiceCore()
        first = service.start_request("conversation:1")
        second = service.start_request("conversation:2")
        event = service.publish_legacy_tool_request(first.request_id, self.event())
        with self.assertRaises(ValueError):
            service.choose_tool_option(second.request_id, event["decision_id"], 0)

    def test_cancel_while_awaiting_tool_invalidates_decision(self):
        service = AgentServiceCore()
        context = service.start_request("conversation:1")
        event = service.publish_legacy_tool_request(context.request_id, self.event())
        self.assertTrue(service.cancel_request(context.request_id))
        self.assertEqual(service.get_request(context.request_id).state, RequestState.CANCEL_REQUESTED)
        with self.assertRaises(ValueError):
            service.choose_tool_option(context.request_id, event["decision_id"], 1)
        summary = service.acknowledge_cancelled(context.request_id)
        self.assertIn("before any recorded external effect", summary)

    def test_cancel_after_external_commit_does_not_claim_rollback(self):
        service = AgentServiceCore()
        context = service.start_request("conversation:1")
        event = service.publish_legacy_tool_request(context.request_id, self.event())
        service.choose_tool_option(context.request_id, event["decision_id"], 1)
        service.mark_external_effect_committed(context.request_id)
        service.cancel_request(context.request_id)
        summary = service.acknowledge_cancelled(context.request_id)
        self.assertIn("may continue", summary)
        self.assertIn("does not roll it back", summary)

    def test_terminal_request_cancel_is_noop(self):
        service = AgentServiceCore()
        context = service.start_request("conversation:1")
        service.complete_request(context.request_id)
        self.assertFalse(service.cancel_request(context.request_id))


if __name__ == "__main__":
    unittest.main()
