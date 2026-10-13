import unittest

from meo.service.backend_adapter import ModelInfo
from meo.service.core import AgentServiceCore


class CatalogBackend:
    def list_models(self):
        return [
            ModelInfo(
                model_id="text-model",
                label="Text model",
                provider="example",
                selection_scope="request",
                selected=True,
                supports_vision=False,
            ),
            ModelInfo(
                model_id="vision-model",
                label="Vision model",
                provider="example",
                selection_scope="request",
                supports_vision=True,
            ),
        ]


class ModelCatalogCapabilityTests(unittest.TestCase):
    def test_service_catalog_exposes_vision_capability_without_guessing_provider(self):
        models = AgentServiceCore(CatalogBackend()).list_models()

        self.assertFalse(models[0]["supports_vision"])
        self.assertTrue(models[1]["supports_vision"])
        self.assertEqual(models[1]["model_id"], "vision-model")
        self.assertEqual(models[1]["provider"], "example")


if __name__ == "__main__":
    unittest.main()
