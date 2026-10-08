import unittest

from meo.service.request_registry import RequestRegistry


class RequestRegistryTests(unittest.TestCase):
    def test_service_generates_unique_request_ids(self):
        registry = RequestRegistry()
        first = registry.create()
        second = registry.create()
        self.assertNotEqual(first.request_id, second.request_id)
        self.assertTrue(first.request_id.startswith("request:"))
        self.assertTrue(registry.contains(first.request_id))

    def test_unknown_request_is_rejected(self):
        registry = RequestRegistry()
        with self.assertRaisesRegex(ValueError, "unknown request_id"):
            registry.get("request:missing")


if __name__ == "__main__":
    unittest.main()
