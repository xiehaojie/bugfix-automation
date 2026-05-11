import tempfile
import unittest
from pathlib import Path

from bugfix_automation.worktree import create_no_push_git_wrapper, install_no_push_hook, worktree_path_for_branch


class WorktreeTest(unittest.TestCase):
    def test_worktree_path_for_branch_is_stable(self) -> None:
        root = Path("/tmp/worktrees")

        self.assertEqual(worktree_path_for_branch(root, "fix/bug-87-demo"), root / "fix-bug-87-demo")

    def test_no_push_git_wrapper_blocks_push_textually(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wrapper_dir = create_no_push_git_wrapper(Path(tmp))
            wrapper = wrapper_dir / "git"

            content = wrapper.read_text(encoding="utf-8")

        self.assertIn("git push is disabled", content)
        self.assertIn('if [ "$1" = "push" ]', content)

    def test_pre_push_hook_blocks_push(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hook = install_no_push_hook(Path(tmp))

            content = hook.read_text(encoding="utf-8")

        self.assertEqual(hook.name, "pre-push")
        self.assertIn("git push is disabled", content)


if __name__ == "__main__":
    unittest.main()
