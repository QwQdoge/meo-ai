from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


class PackagingContractTests(unittest.TestCase):
    def test_meson_includes_every_compatibility_engine_module(self):
        # Source imports can pass while an installed engine fails because a
        # newly imported module was omitted from the explicit install lists.
        source = ROOT / "src"
        declared = set(re.findall(r"'([^']+\.py)'", (source / "meson.build").read_text()))
        modules = {str(path.relative_to(source)) for path in source.rglob("*.py")}
        self.assertEqual(modules - declared, set())

    def test_user_unit_stays_unprivileged_and_loopback_only(self):
        text = (ROOT / "meo/packaging/meo-agent-service.service.in").read_text(encoding="utf-8")
        self.assertIn("ExecStart=@bindir@/meo-agent-service --host 127.0.0.1 --port 8765", text)
        self.assertIn("NoNewPrivileges=yes", text)
        self.assertNotIn("User=root", text)
        self.assertNotIn("--host 0.0.0.0", text)
        self.assertNotIn("--host ::", text.replace("--host ::1", ""))

    def test_installed_launcher_uses_headless_backend_by_default(self):
        text = (ROOT / "meo/packaging/meo-agent-service.in").read_text(encoding="utf-8")
        self.assertIn("meo.adapters.headless_newelle:create_backend", text)
        self.assertIn("from meo.runtime.main import main", text)
        self.assertNotIn("src.main", text)

    def test_packaging_does_not_enable_unit_during_install(self):
        meson = (ROOT / "meo/packaging/meson.build").read_text(encoding="utf-8")
        self.assertIn("systemd', 'user", meson)
        self.assertNotIn("systemctl", meson)
        self.assertNotIn("enable", meson.lower())


if __name__ == "__main__":
    unittest.main()
