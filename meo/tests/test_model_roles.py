import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from meo.service.backend_adapter import ModelInfo
from meo.service.model_roles import ModelRoleRegistry


class ModelRoleRegistryTests(unittest.TestCase):
    def setUp(self):
        self.models = [
            ModelInfo("cheap:tiny", "Tiny", "Cheap", selected=False),
            ModelInfo("main:strong", "Strong", "Main", selected=True),
        ]

    def test_profile_models_remain_preference_only(self):
        roles = ModelRoleRegistry().list_roles(self.models)
        self.assertEqual(
            [item["role_id"] for item in roles],
            ["chat", "reasoning", "execution", "vision", "judge", "title"],
        )
        self.assertTrue(all(item["fallback_model_id"] == "main:strong" for item in roles))
        self.assertTrue(all(item["routing_status"] == "preference_only" for item in roles))
        self.assertTrue(all(item["runtime_supported"] is False for item in roles))

    def test_request_scoped_catalog_reports_active_routing(self):
        models = [
            ModelInfo("cheap:tiny", "Tiny", "Cheap", selection_scope="request", selected=False),
            ModelInfo("main:strong", "Strong", "Main", selection_scope="request", selected=True),
        ]
        roles = ModelRoleRegistry().list_roles(models)
        self.assertTrue(all(item["routing_status"] == "active" for item in roles))
        self.assertTrue(all(item["runtime_supported"] is True for item in roles))
        self.assertTrue(all(item["selection_scope"] == "request" for item in roles))

    def test_assignment_validates_model_catalog_persists_and_resolves(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model-roles.json"
            registry = ModelRoleRegistry(path)
            role = registry.set_role("title", "cheap:tiny", self.models)
            self.assertEqual(role["preferred_model_id"], "cheap:tiny")
            self.assertTrue(role["preferred_available"])
            self.assertEqual(registry.resolve_model("title", self.models), ("cheap:tiny", False))

            restored = ModelRoleRegistry(path)
            restored_title = next(item for item in restored.list_roles(self.models) if item["role_id"] == "title")
            self.assertEqual(restored_title["preferred_model_id"], "cheap:tiny")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 2)
            self.assertEqual(payload["assignments"]["title"], "cheap:tiny")

    def test_missing_preferred_model_falls_back_and_marks_fallback(self):
        registry = ModelRoleRegistry()
        registry.set_role("judge", "cheap:tiny", self.models)
        current_only = [ModelInfo("main:strong", "Strong", "Main", selected=True)]
        self.assertEqual(registry.resolve_model("judge", current_only), ("main:strong", True))

    def test_unknown_roles_and_models_are_rejected(self):
        registry = ModelRoleRegistry()
        with self.assertRaisesRegex(ValueError, "unknown model role"):
            registry.set_role("security", "main:strong", self.models)
        with self.assertRaisesRegex(ValueError, "unknown model_id"):
            registry.set_role("judge", "missing:model", self.models)

    def test_null_or_blank_assignment_restores_default_fallback(self):
        registry = ModelRoleRegistry()
        registry.set_role("execution", "cheap:tiny", self.models)
        role = registry.set_role("execution", None, self.models)
        self.assertEqual(role["preferred_model_id"], "")
        self.assertEqual(role["fallback_model_id"], "main:strong")
        self.assertEqual(registry.resolve_model("execution", self.models), ("main:strong", False))


if __name__ == "__main__":
    unittest.main()
