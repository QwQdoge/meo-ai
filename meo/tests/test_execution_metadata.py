from __future__ import annotations

import unittest

from meo.service.response_meta import normalize_response_meta


class ExecutionMetadataTests(unittest.TestCase):
    def test_execution_runtime_details_are_first_class(self) -> None:
        normalized = normalize_response_meta({
            "type": "response_meta",
            "routing": {
                "role_id": "execution",
                "model_id": "main:exec",
                "complexity": "high",
                "fallback_used": False,
            },
            "coordination": {
                "run_id": "local:123",
                "status": "completed",
                "model_id": "main:reason",
                "tasks": [
                    {"title": "Architecture", "status": "completed"},
                    {"title": "Tests", "status": "completed"},
                ],
            },
            "verification": {
                "status": "accepted_after_repair",
                "judge_model_id": "cheap:judge",
                "repair_count": 1,
                "attempts": [
                    {"verdict": "REVISE", "issues": ["Missing validation"], "confidence": 0.8},
                    {"verdict": "ACCEPT", "issues": [], "confidence": 0.95},
                ],
            },
            "activity": {
                "coordination": {"used": True, "status": "completed", "task_count": 2},
                "verification": {"used": True, "status": "accepted_after_repair"},
            },
        })

        self.assertEqual(normalized["routing"]["role_id"], "execution")
        self.assertEqual(normalized["coordination"]["tasks"][0]["title"], "Architecture")
        self.assertEqual(normalized["verification"]["judge_model_id"], "cheap:judge")
        self.assertEqual(normalized["activity"]["coordination"]["task_count"], 2)
        self.assertEqual(normalized["activity"]["verification"]["status"], "accepted_after_repair")
        self.assertNotIn("routing", normalized.get("extra", {}))
        self.assertNotIn("coordination", normalized.get("extra", {}))
        self.assertNotIn("verification", normalized.get("extra", {}))

    def test_runtime_details_are_secret_filtered(self) -> None:
        normalized = normalize_response_meta({
            "coordination": {
                "status": "failed",
                "api_key": "should-not-leak",
                "tasks": [{"title": "Check", "status": "failed"}],
            },
            "verification": {
                "status": "unavailable",
                "reason": "provider unavailable",
                "Authorization": "Bearer private",
            },
        })

        self.assertEqual(normalized["coordination"]["api_key"], "<redacted>")
        self.assertEqual(normalized["verification"]["Authorization"], "<redacted>")
        self.assertEqual(normalized["verification"]["reason"], "provider unavailable")

    def test_unrelated_unknown_fields_still_remain_in_extra(self) -> None:
        normalized = normalize_response_meta({
            "future_backend_field": {"version": 4},
            "activity": {"coordination": {"used": False}},
        })
        self.assertEqual(normalized["extra"]["future_backend_field"], {"version": 4})
        self.assertFalse(normalized["activity"]["coordination"]["used"])


if __name__ == "__main__":
    unittest.main()
