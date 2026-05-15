import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class VersionCliTests(unittest.TestCase):
    def test_cli_version_reports_semver_and_exits_without_root(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "udev-autoconfig.py"), "--version"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertRegex(
            result.stdout,
            r"^udev-autoconfig(?:\.py)? \d+\.\d+\.\d+\n$",
        )


if __name__ == "__main__":
    unittest.main()
