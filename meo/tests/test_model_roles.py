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

    def test_roles_fall_back_to_current_selected_model_without_claiming_runtime_routing(self):
        roles = ModelRoleRegistry().list_roles(self.models)
        self.assertEqual([item["role_id"] for item in roles], ["title", "judge", "reasoning", "execution"])
        self.assertTrue(all(item["fallback_model_id"] == "main:strong" for item in roles))
        self.assertTrue(all(item["routing_status"] == "preference_only" for item in roles))
        self.assertTrue(all(item["runtime_supported"] is False for item in roles))

    def test_assignment_validates_model_catalog_and_persists(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model-roles.json"
            registry = ModelRoleRegistry(path)
            role = registry.set_role("title", "cheap:tiny", self.models)
            self.assertEqual(role["preferred_model_id"], "cheap:tiny")
            self.assertTrue(role["preferred_available"])

            restored = ModelRoleRegistry(path)
            restored_title = next(item for item in restored.list_roles(self.models) if item["role_id"] == "title")
            self.assertEqual(restored_title["preferred_model_id"], "cheap:tiny")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["assignments"]["title"], "cheap:tiny")

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


if __name__ == "__main__":
    unittest.main()
