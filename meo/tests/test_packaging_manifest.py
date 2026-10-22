"""Every runtime Python module must be installed by packaging/meson.build.

The install list is explicit, so a new module that is not added to it passes
the source tests but fails at runtime from the packaged tree with
ModuleNotFoundError.
"""

import re
import unittest
from pathlib import Path

MEO_ROOT = Path(__file__).resolve().parents[1]
MESON = MEO_ROOT / "packaging" / "meson.build"


class PackagingManifestTests(unittest.TestCase):
    def test_every_module_in_packaged_directories_is_installed(self):
        listed = set(re.findall(r"'\.\./([\w/]+\.py)'", MESON.read_text(encoding="utf-8")))
        self.assertTrue(listed)
        packaged_dirs = {Path(item).parent for item in listed}
        missing = sorted(
            str(path.relative_to(MEO_ROOT))
            for directory in packaged_dirs
            for path in (MEO_ROOT / directory).glob("*.py")
            if str(path.relative_to(MEO_ROOT)) not in listed
        )
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
