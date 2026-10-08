import unittest

from meo.service.legacy_v2_bridge import LegacyV2ToolBridge
from meo.service.request_state import RequestLifecycle, RequestState


class LegacyV2ToolBridgeTests(unittest.TestCase):
    def running_request(self, request_id="r1"):
        req = RequestLifecycle(request_id)
        req.transition(RequestState.RUNNING_MODEL)
        return req

    def event(self):
        return {
            "type": "tool_interaction",
            "tool_name": "file",
            "interaction_id": "legacy-i1",
            "display_text": "Review target before continuing",
            "options": [
                {"index": 4, "title": "Deny"},
                {"index": 9, "title": "Approve"},
            ],
        }

    def test_publish_reissues_service_decision_id(self):
        bridge = LegacyV2ToolBridge()
        req = self.running_request()
        normalized = bridge.publish(req, self.event())
        self.assertEqual(req.state, RequestState.AWAITING_TOOL)
        self.assertEqual(normalized["type"], "tool.requested")
        self.assertTrue(normalized["decision_id"].startswith("decision:"))
        self.assertNotEqual(normalized["decision_id"], "legacy-i1")
        self.assertEqual(normalized["compatibility"]["interaction_id"], "legacy-i1")
        self.assertEqual(normalized["display_text"], "Review target before continuing")

    def test_non_interactive_result_becomes_completion_event_without_decision(self):
        bridge = LegacyV2ToolBridge()
        req = self.running_request()
        normalized = bridge.publish_result(
            req,
            {
                "type": "tool_result",
                "tool_name": "system_org_meo_desktop_audio_get_volume",
                "display_text": "Read volume",
            },
        )
        self.assertEqual(req.state, RequestState.RUNNING_MODEL)
        self.assertEqual(normalized["type"], "tool.completed")
        self.assertEqual(normalized["request_id"], req.request_id)
        self.assertNotIn("decision_id", normalized)

    def test_display_text_is_bounded_and_never_decision_authority(self):
        bridge = LegacyV2ToolBridge()
        req = self.running_request()
        event = self.event()
        event["display_text"] = "x" * 5000
        normalized = bridge.publish(req, event)
        self.assertEqual(len(normalized["display_text"]), 4000)
        self.assertTrue(normalized["decision_id"].startswith("decision:"))

    def test_result_display_text_is_also_bounded(self):
        bridge = LegacyV2ToolBridge()
        req = self.running_request()
        normalized = bridge.publish_result(
            req,
            {"type": "tool_result", "tool_name": "read", "display_text": "x" * 5000},
        )
        self.assertEqual(len(normalized["display_text"]), 4000)

    def test_resolve_maps_frontend_position_to_legacy_index(self):
        bridge = LegacyV2ToolBridge()
        req = self.running_request()
        normalized = bridge.publish(req, self.event())
        legacy_index = bridge.resolve(req, normalized["decision_id"], 1)
        self.assertEqual(legacy_index, 9)

    def test_late_reply_after_cancel_is_rejected(self):
        bridge = LegacyV2ToolBridge()
        req = self.running_request()
        normalized = bridge.publish(req, self.event())
        req.request_cancel()
        bridge.cancel(req)
        with self.assertRaises(ValueError):
            bridge.resolve(req, normalized["decision_id"], 1)

    def test_malformed_event_never_becomes_approval(self):
        bridge = LegacyV2ToolBridge()
        req = self.running_request()
        bad = self.event()
        bad["options"] = [{"index": True, "title": "Approve"}]
        with self.assertRaises(ValueError):
            bridge.publish(req, bad)

    def test_non_string_display_text_is_rejected(self):
        bridge = LegacyV2ToolBridge()
        req = self.running_request()
        bad = self.event()
        bad["display_text"] = {"pretend": "trusted"}
        with self.assertRaises(ValueError):
            bridge.publish(req, bad)


if __name__ == "__main__":
    unittest.main()
