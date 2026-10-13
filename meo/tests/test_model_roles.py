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
            ModelInfo("main:strong", "Strong", "Main", selected=True, supports_vision=True),
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
        vision = next(item for item in roles if item["role_id"] == "vision")
        self.assertEqual(vision["eligible_model_ids"], ["main:strong"])
        self.assertTrue(vision["capability_available"])

    def test_request_scoped_catalog_reports_active_routing(self):
        models = [
            ModelInfo("cheap:tiny", "Tiny", "Cheap", selection_scope="request", selected=False),
            ModelInfo(
                "main:strong",
                "Strong",
                "Main",
                selection_scope="request",
                selected=True,
                supports_vision=True,
            ),
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

    def test_vision_role_rejects_text_only_model(self):
        registry = ModelRoleRegistry()
        with self.assertRaisesRegex(ValueError, "does not support vision inputs"):
            registry.set_role("vision", "cheap:tiny", self.models)
        role = next(item for item in registry.list_roles(self.models) if item["role_id"] == "vision")
        self.assertEqual(role["preferred_model_id"], "")
        self.assertEqual(role["fallback_model_id"], "main:strong")

    def test_vision_role_reports_missing_capability_honestly(self):
        models = [ModelInfo("text:only", "Text", "Text", selection_scope="request", selected=True)]
        registry = ModelRoleRegistry()
        role = next(item for item in registry.list_roles(models) if item["role_id"] == "vision")
        self.assertFalse(role["capability_available"])
        self.assertFalse(role["runtime_supported"])
        self.assertEqual(role["fallback_model_id"], "")
        self.assertEqual(role["eligible_model_ids"], [])
        with self.assertRaisesRegex(ValueError, "no vision-capable model"):
            registry.resolve_model("vision", models)

    def test_stale_text_only_vision_assignment_falls_back_to_capable_model(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model-roles.json"
            path.write_text(
                json.dumps({"version": 2, "assignments": {"vision": "cheap:tiny"}}),
                encoding="utf-8",
            )
            registry = ModelRoleRegistry(path)
            self.assertEqual(registry.resolve_model("vision", self.models), ("main:strong", True))
            role = next(item for item in registry.list_roles(self.models) if item["role_id"] == "vision")
            self.assertEqual(role["preferred_model_id"], "cheap:tiny")
            self.assertFalse(role["preferred_available"])

    def test_null_or_blank_assignment_restores_default_fallback(self):
        registry = ModelRoleRegistry()
        registry.set_role("execution", "cheap:tiny", self.models)
        role = registry.set_role("execution", None, self.models)
        self.assertEqual(role["preferred_model_id"], "")
        self.assertEqual(role["fallback_model_id"], "main:strong")
        self.assertEqual(registry.resolve_model("execution", self.models), ("main:strong", False))


if __name__ == "__main__":
    unittest.main()
