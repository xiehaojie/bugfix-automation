import tempfile
import unittest
from pathlib import Path
import subprocess

from bugfix_automation.worktree import create_no_push_git_wrapper, rename_current_branch, worktree_path_for_branch


class WorktreeTest(unittest.TestCase):
    def test_worktree_path_for_branch_is_stable(self) -> None:
        root = Path("/tmp/worktrees")

        self.assertEqual(worktree_path_for_branch(root, "fix/bug-87-demo"), root / "fix-bug-87-demo")

    def test_no_push_git_wrapper_blocks_push_textually(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wrapper_dir = create_no_push_git_wrapper(Path(tmp))
            wrapper = wrapper_dir / "git"

            content = wrapper.read_text(encoding="utf-8")

        self.assertIn("自动修复流程已禁止 git push", content)
        self.assertIn('if [ "$1" = "push" ]', content)

    def test_rename_current_branch_renames_checked_out_fix_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            (repo / "a.txt").write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "checkout", "-b", "fix/bug-24-temp"], cwd=repo, check=True, stdout=subprocess.DEVNULL)

            rename_current_branch(repo, "fix/24-update-favorites-list")

            branch = subprocess.run(["git", "branch", "--show-current"], cwd=repo, text=True, capture_output=True, check=True)

        self.assertEqual(branch.stdout.strip(), "fix/24-update-favorites-list")

if __name__ == "__main__":
    unittest.main()
