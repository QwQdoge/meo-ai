from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from meo.cloud.server import CloudServerConfig, _normalized_origin


class CloudOriginTests(unittest.TestCase):
    def test_https_origin_is_normalized(self) -> None:
        self.assertEqual(
            _normalized_origin("https://account.meoarch.org/", label="test"),
            "https://account.meoarch.org",
        )

    def test_loopback_http_is_allowed_for_development(self) -> None:
        self.assertEqual(
            _normalized_origin("http://localhost:8080", label="test"),
            "http://localhost:8080",
        )

    def test_public_http_is_rejected(self) -> None:
        with self.assertRaises(RuntimeError):
            _normalized_origin("http://account.meoarch.org", label="test")

    def test_origin_with_path_or_credentials_is_rejected(self) -> None:
        for value in (
            "https://account.meoarch.org/connect-device",
            "https://user@example.com",
            "https://account.meoarch.org/?x=1",
        ):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                _normalized_origin(value, label="test")

    def test_config_always_includes_account_origin_and_deduplicates(self) -> None:
        env = {
            "MEO_SUPABASE_URL": "https://example.supabase.co",
            "MEO_SUPABASE_PUBLISHABLE_KEY": "publishable",
            "MEO_SUPABASE_SERVICE_ROLE_KEY": "service-role",
            "MEO_ACCOUNT_URL": "https://account.meoarch.org",
            "MEO_ALLOWED_WEB_ORIGINS": "https://chat.meoarch.org,https://account.meoarch.org",
        }
        with patch.dict(os.environ, env, clear=True):
            config = CloudServerConfig.from_env()
        self.assertEqual(
            config.allowed_web_origins,
            ("https://account.meoarch.org", "https://chat.meoarch.org"),
        )


if __name__ == "__main__":
    unittest.main()
