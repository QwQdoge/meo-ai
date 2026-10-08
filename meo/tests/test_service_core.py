import unittest

from meo.service.core import AgentServiceCore
from meo.service.request_state import RequestState


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
