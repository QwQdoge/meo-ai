import unittest

from meo.service.request_state import RequestLifecycle, RequestState
from meo.service.tool_decision import DecisionState, ToolDecisionRegistry


class ToolDecisionRegistryTests(unittest.TestCase):
    def awaiting_request(self, request_id="r1"):
        req = RequestLifecycle(request_id)
        req.transition(RequestState.RUNNING_MODEL)
        req.transition(RequestState.AWAITING_TOOL)
        return req

    def test_service_issues_unique_decision_ids(self):
        registry = ToolDecisionRegistry()
        first = registry.issue(self.awaiting_request("r1"), ["approve", "deny"])
        second = registry.issue(self.awaiting_request("r2"), ["approve", "deny"])
        self.assertNotEqual(first.decision_id, second.decision_id)
        self.assertTrue(first.decision_id.startswith("decision:"))

    def test_resolve_requires_matching_request(self):
        registry = ToolDecisionRegistry()
        owner = self.awaiting_request("owner")
        other = self.awaiting_request("other")
        decision = registry.issue(owner, ["approve", "deny"])
        with self.assertRaisesRegex(ValueError, "does not belong"):
            registry.resolve(other, decision.decision_id, 0)

    def test_reissuing_invalidates_previous_decision(self):
        registry = ToolDecisionRegistry()
        req = self.awaiting_request()
        first = registry.issue(req, ["approve", "deny"])
        second = registry.issue(req, ["continue", "stop"])
        self.assertEqual(first.state, DecisionState.INVALIDATED)
        with self.assertRaisesRegex(ValueError, "stale"):
            registry.resolve(req, first.decision_id, 0)
        self.assertEqual(registry.resolve(req, second.decision_id, 1), "stop")

    def test_decision_cannot_be_replayed(self):
        registry = ToolDecisionRegistry()
        req = self.awaiting_request()
        decision = registry.issue(req, ["approve", "deny"])
        self.assertEqual(registry.resolve(req, decision.decision_id, 0), "approve")
        with self.assertRaises(ValueError):
            registry.resolve(req, decision.decision_id, 0)

    def test_cancel_invalidation_rejects_late_frontend_reply(self):
        registry = ToolDecisionRegistry()
        req = self.awaiting_request()
        decision = registry.issue(req, ["approve", "deny"])
        req.request_cancel()
        registry.invalidate_for_request(req.request_id)
        self.assertEqual(decision.state, DecisionState.INVALIDATED)
        with self.assertRaises(ValueError):
            registry.resolve(req, decision.decision_id, 0)

    def test_empty_options_are_rejected(self):
        registry = ToolDecisionRegistry()
        with self.assertRaises(ValueError):
            registry.issue(self.awaiting_request(), [])


if __name__ == "__main__":
    unittest.main()
