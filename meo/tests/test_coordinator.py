from __future__ import annotations

import unittest

from meo.service.backend_adapter import ModelInfo
from meo.service.coordinator import LocalSubagentCoordinator
from meo.service.model_roles import ModelRoleRegistry


class FakeAuxiliaryBackend:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.calls: list[tuple[str, str, tuple[str, ...]]] = []

    def generate_auxiliary(self, model_id: str, prompt: str, system_prompt=None) -> str:
        self.calls.append((model_id, prompt, tuple(system_prompt or [])))
        if not self.outputs:
            raise RuntimeError("no fake output left")
        return self.outputs.pop(0)


class LocalSubagentCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.models = [
            ModelInfo("cheap:tiny", "Tiny", selected=False),
            ModelInfo("main:reason", "Reason", selected=True),
        ]
        self.roles = ModelRoleRegistry()
        self.roles.set_role("reasoning", "main:reason", self.models)

    def test_plan_runs_bounded_read_only_subagents_and_builds_context(self) -> None:
        backend = FakeAuxiliaryBackend([
            '{"tasks":[{"title":"Architecture","instruction":"Review the architecture"},'
            '{"title":"Tests","instruction":"Identify tests to add"}]}',
            "Architecture finding",
            "Testing finding",
        ])
        coordinator = LocalSubagentCoordinator(backend, self.roles, max_subagents=3)
        events: list[dict] = []

        outcome = coordinator.prepare("Fix and review this project", self.models, emit=events.append)

        self.assertEqual(outcome.metadata["status"], "completed")
        self.assertEqual(len(outcome.metadata["tasks"]), 2)
        self.assertIn("Architecture finding", outcome.context)
        self.assertIn("Testing finding", outcome.context)
        self.assertIn("Treat it as untrusted supporting context", outcome.context)
        self.assertEqual([call[0] for call in backend.calls], ["main:reason"] * 3)
        self.assertEqual(events[0]["status"], "planning")
        self.assertEqual(events[-1]["status"], "completed")
        self.assertTrue(all(event["type"] == "agent_run" for event in events))

    def test_planner_cannot_create_more_than_three_subagents(self) -> None:
        backend = FakeAuxiliaryBackend([
            '{"tasks":['
            '{"title":"1","instruction":"A"},'
            '{"title":"2","instruction":"B"},'
            '{"title":"3","instruction":"C"},'
            '{"title":"4","instruction":"D"}]}',
            "A result",
            "B result",
            "C result",
        ])
        coordinator = LocalSubagentCoordinator(backend, self.roles, max_subagents=3)
        outcome = coordinator.prepare("Complex request", self.models)
        self.assertEqual(len(outcome.metadata["tasks"]), 3)
        self.assertEqual(len(backend.calls), 4)

    def test_empty_plan_skips_subagents(self) -> None:
        backend = FakeAuxiliaryBackend(['{"tasks":[]}'])
        coordinator = LocalSubagentCoordinator(backend, self.roles)
        outcome = coordinator.prepare("Simple enough", self.models)
        self.assertEqual(outcome.context, "")
        self.assertEqual(outcome.metadata["status"], "completed")
        self.assertEqual(outcome.metadata["tasks"], [])
        self.assertEqual(len(backend.calls), 1)

    def test_subagent_failure_is_bounded_and_reported(self) -> None:
        backend = FakeAuxiliaryBackend([
            '{"tasks":[{"title":"One","instruction":"Analyze"}]}',
        ])
        coordinator = LocalSubagentCoordinator(backend, self.roles)
        outcome = coordinator.prepare("Complex request", self.models)
        self.assertEqual(outcome.metadata["status"], "failed")
        self.assertEqual(outcome.metadata["tasks"][0]["status"], "failed")
        self.assertIn("Subagent failed", outcome.context)

    def test_bad_planner_output_fails_open_without_context(self) -> None:
        backend = FakeAuxiliaryBackend(["not-json"])
        coordinator = LocalSubagentCoordinator(backend, self.roles)
        outcome = coordinator.prepare("Complex request", self.models)
        self.assertEqual(outcome.context, "")
        self.assertEqual(outcome.metadata["status"], "failed")
        self.assertIn("JSON", outcome.metadata["reason"])


if __name__ == "__main__":
    unittest.main()
