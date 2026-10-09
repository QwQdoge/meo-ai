from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from meo.device.agentd import AgentdConfig
from meo.device.config import load_agentd_config, relay_url_from_cloud, save_agentd_config
from meo.device.protocol import DeviceRegistration


class DeviceConfigTests(unittest.TestCase):
    def test_cloud_https_becomes_secure_relay_url(self) -> None:
        self.assertEqual(
            relay_url_from_cloud("https://ai.meoarch.org"),
            "wss://ai.meoarch.org/v1/device-relay",
        )

    def test_loopback_http_becomes_ws_for_development(self) -> None:
        self.assertEqual(
            relay_url_from_cloud("http://localhost:8080/api"),
            "ws://localhost:8080/api/v1/device-relay",
        )

    def test_public_http_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            relay_url_from_cloud("http://ai.meoarch.org")

    def test_saved_config_contains_no_device_secret_and_round_trips(self) -> None:
        config = AgentdConfig(
            device=DeviceRegistration.create(
                "legion-y9000x",
                "Legion Y9000X",
                ("agent.chat",),
            ),
            relay_url="wss://ai.meoarch.org/v1/device-relay",
        )
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "meo" / "agentd.json"
            saved = save_agentd_config(config, path)
            raw = saved.read_text(encoding="utf-8")
            value = json.loads(raw)
            self.assertNotIn("device_token", value)
            self.assertNotIn("token", value)
            self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
            restored = load_agentd_config(saved)
        self.assertEqual(restored.device.device_id, "legion-y9000x")
        self.assertEqual(restored.relay_url, "wss://ai.meoarch.org/v1/device-relay")


if __name__ == "__main__":
    unittest.main()
