from __future__ import annotations

import unittest

from meo.service.backend_adapter import ModelInfo
from meo.service.model_roles import ModelRoleRegistry
from meo.service.verification import JudgeVerifier


class FakeAuxiliaryBackend:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.calls: list[tuple[str, str, tuple[str, ...]]] = []

    def generate_auxiliary(self, model_id: str, prompt: str, system_prompt=None) -> str:
        self.calls.append((model_id, prompt, tuple(system_prompt or [])))
        if not self.outputs:
            raise RuntimeError("no fake output left")
        return self.outputs.pop(0)


class JudgeVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.models = [
            ModelInfo("cheap:judge", "Judge", selected=False),
            ModelInfo("main:exec", "Execution", selected=True),
        ]
        self.roles = ModelRoleRegistry()
        self.roles.set_role("judge", "cheap:judge", self.models)

    def test_accept_returns_candidate_without_repair(self) -> None:
        backend = FakeAuxiliaryBackend([
            '{"verdict":"ACCEPT","issues":[],"confidence":0.94}',
        ])
        verifier = JudgeVerifier(backend, self.roles)
        outcome = verifier.verify("Fix it", "Done correctly", self.models, "main:exec")
        self.assertEqual(outcome.text, "Done correctly")
        self.assertEqual(outcome.metadata["status"], "accepted")
        self.assertTrue(outcome.metadata["checked"])
        self.assertTrue(outcome.metadata["verified"])
        self.assertEqual(outcome.metadata["repair_count"], 0)
        self.assertEqual([call[0] for call in backend.calls], ["cheap:judge"])

    def test_revise_repairs_then_rechecks_once(self) -> None:
        backend = FakeAuxiliaryBackend([
            '{"verdict":"REVISE","issues":["Missing validation"],"confidence":0.8}',
            "Corrected answer with validation",
            '{"verdict":"ACCEPT","issues":[],"confidence":0.9}',
        ])
        verifier = JudgeVerifier(backend, self.roles, max_repairs=1)
        outcome = verifier.verify("Implement feature", "Initial answer", self.models, "main:exec")
        self.assertEqual(outcome.text, "Corrected answer with validation")
        self.assertEqual(outcome.metadata["status"], "accepted_after_repair")
        self.assertTrue(outcome.metadata["checked"])
        self.assertTrue(outcome.metadata["verified"])
        self.assertEqual(outcome.metadata["repair_count"], 1)
        self.assertEqual(
            [call[0] for call in backend.calls],
            ["cheap:judge", "main:exec", "cheap:judge"],
        )
        self.assertIn("Missing validation", backend.calls[1][1])

    def test_second_rejection_is_bounded_and_visibly_unverified(self) -> None:
        backend = FakeAuxiliaryBackend([
            '{"verdict":"REVISE","issues":["A"],"confidence":0.7}',
            "Repair attempt",
            '{"verdict":"REVISE","issues":["B"],"confidence":0.6}',
        ])
        verifier = JudgeVerifier(backend, self.roles, max_repairs=1)
        outcome = verifier.verify("Do it", "Candidate", self.models, "main:exec")
        self.assertIn("Verification warning:", outcome.text)
        self.assertTrue(outcome.text.endswith("Repair attempt"))
        self.assertEqual(outcome.metadata["status"], "rejected_after_repair")
        self.assertTrue(outcome.metadata["checked"])
        self.assertFalse(outcome.metadata["verified"])
        self.assertEqual(len(outcome.metadata["attempts"]), 2)
        self.assertEqual(len(backend.calls), 3)

    def test_bad_judge_output_fails_open_but_marks_result_unchecked(self) -> None:
        backend = FakeAuxiliaryBackend(["not-json"])
        verifier = JudgeVerifier(backend, self.roles)
        outcome = verifier.verify("Do it", "Candidate", self.models, "main:exec")
        self.assertIn("Verification unavailable:", outcome.text)
        self.assertTrue(outcome.text.endswith("Candidate"))
        self.assertEqual(outcome.metadata["status"], "unavailable")
        self.assertFalse(outcome.metadata["checked"])
        self.assertFalse(outcome.metadata["verified"])
        self.assertIn("JSON", outcome.metadata["reason"])

    def test_repair_failure_keeps_original_with_visible_warning(self) -> None:
        backend = FakeAuxiliaryBackend([
            '{"verdict":"REVISE","issues":["A"],"confidence":0.7}',
        ])
        verifier = JudgeVerifier(backend, self.roles, max_repairs=1)
        outcome = verifier.verify("Do it", "Original candidate", self.models, "main:exec")
        self.assertIn("Verification warning:", outcome.text)
        self.assertTrue(outcome.text.endswith("Original candidate"))
        self.assertEqual(outcome.metadata["status"], "repair_failed")
        self.assertTrue(outcome.metadata["checked"])
        self.assertFalse(outcome.metadata["verified"])

    def test_markdown_json_fence_is_accepted(self) -> None:
        backend = FakeAuxiliaryBackend([
            '```json\n{"verdict":"ACCEPT","issues":[],"confidence":1}\n```',
        ])
        verifier = JudgeVerifier(backend, self.roles)
        outcome = verifier.verify("Do it", "Candidate", self.models, "main:exec")
        self.assertEqual(outcome.metadata["status"], "accepted")
        self.assertTrue(outcome.metadata["verified"])


if __name__ == "__main__":
    unittest.main()