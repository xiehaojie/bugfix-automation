import unittest
from pathlib import Path
from unittest.mock import patch

from bugfix_automation.scheduler import resolve_codex_bin


class SchedulerTest(unittest.TestCase):
    def test_resolve_codex_bin_fails_without_absolute_path(self) -> None:
        with patch("bugfix_automation.scheduler.shutil.which", return_value=None):
            with patch.object(Path, "exists", return_value=False):
                with self.assertRaisesRegex(FileNotFoundError, "Codex CLI not found"):
                    resolve_codex_bin("codex")

    def test_resolve_codex_bin_keeps_absolute_path(self) -> None:
        self.assertEqual(resolve_codex_bin("/tmp/codex"), "/tmp/codex")


if __name__ == "__main__":
    unittest.main()
