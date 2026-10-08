import unittest

from meo.service.request_state import RequestLifecycle, RequestState


class RequestLifecycleTests(unittest.TestCase):
    def test_model_to_tool_to_model_to_complete(self):
        req = RequestLifecycle("r1")
        req.transition(RequestState.RUNNING_MODEL)
        req.transition(RequestState.AWAITING_TOOL)
        req.transition(RequestState.RUNNING_TOOL)
        req.transition(RequestState.RUNNING_MODEL)
        req.transition(RequestState.COMPLETED)
        self.assertTrue(req.terminal)

    def test_cancel_blocks_new_work(self):
        req = RequestLifecycle("r2")
        req.transition(RequestState.RUNNING_MODEL)
        req.request_cancel()
        self.assertEqual(req.state, RequestState.CANCEL_REQUESTED)
        self.assertFalse(req.may_start_new_work)
        with self.assertRaises(ValueError):
            req.transition(RequestState.AWAITING_TOOL)
        req.mark_cancelled()
        self.assertTrue(req.terminal)

    def test_cancel_is_idempotent_before_terminal(self):
        req = RequestLifecycle("r3")
        req.request_cancel()
        req.request_cancel()
        self.assertEqual(req.state, RequestState.CANCEL_REQUESTED)

    def test_cancel_does_not_claim_rollback_after_external_effect(self):
        req = RequestLifecycle("r4")
        req.transition(RequestState.RUNNING_MODEL)
        req.transition(RequestState.AWAITING_TOOL)
        req.transition(RequestState.RUNNING_TOOL)
        req.mark_external_effect_committed()
        req.request_cancel()
        req.mark_cancelled()
        summary = req.cancellation_summary()
        self.assertIn("may continue", summary)
        self.assertIn("does not roll it back", summary)

    def test_invalid_transition_is_rejected(self):
        req = RequestLifecycle("r5")
        with self.assertRaises(ValueError):
            req.transition(RequestState.COMPLETED)


if __name__ == "__main__":
    unittest.main()
