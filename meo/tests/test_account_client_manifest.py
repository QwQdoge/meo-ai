from __future__ import annotations

import json
from pathlib import Path
import unittest


class AccountClientManifestTest(unittest.TestCase):
    def test_meo_ai_broker_access_is_limited_to_native_app_and_agent_service(self) -> None:
        manifest_path = Path(__file__).resolve().parents[1] / "packaging" / "org.meo.MeoAI.account-client.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["id"], "org.meo.MeoAI")
        self.assertEqual(
            manifest["executables"],
            ["/usr/bin/meo-ai", "/usr/bin/meo-agent-service"],
        )
        self.assertIn("local_ai", manifest["capabilities"])
        self.assertIn("ai_usage_sync", manifest["capabilities"])
        self.assertNotIn("*", "".join(manifest["executables"]))


if __name__ == "__main__":
    unittest.main()
