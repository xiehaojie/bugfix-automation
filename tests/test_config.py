import unittest

from bugfix_automation.config import load_config


class ConfigTest(unittest.TestCase):
    def test_default_worktree_root_stays_inside_automation_repo(self) -> None:
        config = load_config()

        self.assertIn("bugfix-automation", str(config.worktree_root))
        self.assertNotIn("/code/monorepo/.worktrees", str(config.worktree_root))


if __name__ == "__main__":
    unittest.main()
