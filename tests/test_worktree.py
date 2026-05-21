import tempfile
import unittest
from pathlib import Path
import subprocess

from bugfix_automation.runner import runtime_path_prefix
from bugfix_automation.worktree import create_no_push_git_wrapper, rename_current_branch, symlink_node_modules, tracked_changed_files, worktree_path_for_branch, write_worktree_exclude


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

    def test_runtime_path_prefix_reuses_target_repo_node_bins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            wrapper = Path(tmp) / "wrapper"
            (repo / "node_modules" / ".bin").mkdir(parents=True)
            (repo / "apps" / "pc-web" / "node_modules" / ".bin").mkdir(parents=True)
            wrapper.mkdir()

            prefix = runtime_path_prefix(repo, wrapper)

        parts = prefix.split(":")
        self.assertEqual(parts[0], str(wrapper))
        self.assertIn(str(repo / "node_modules" / ".bin"), parts)
        self.assertIn(str(repo / "apps" / "pc-web" / "node_modules" / ".bin"), parts)

    def test_node_modules_symlink_is_available_but_ignored_by_changed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            worktree = root / "worktree"
            repo.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            (repo / "apps" / "pc-web" / "src").mkdir(parents=True)
            (repo / "apps" / "pc-web" / "src" / "index.ts").write_text("initial\n", encoding="utf-8")
            (repo / "apps" / "pc-web" / "node_modules" / ".bin").mkdir(parents=True)
            subprocess.run(["git", "add", "apps/pc-web/src/index.ts"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "worktree", "add", str(worktree), "-b", "fix/demo"], cwd=repo, check=True, stdout=subprocess.DEVNULL)

            write_worktree_exclude(worktree)
            symlink_node_modules(worktree, repo)
            (worktree / "apps" / "pc-web" / "src" / "index.ts").write_text("changed\n", encoding="utf-8")

            status = subprocess.run(["git", "status", "--porcelain"], cwd=worktree, text=True, capture_output=True, check=True).stdout
            changed_files = tracked_changed_files(worktree, "apps/pc-web")
            node_modules_is_symlink = (worktree / "apps" / "pc-web" / "node_modules").is_symlink()

        self.assertTrue(node_modules_is_symlink)
        self.assertNotIn("node_modules", status)
        self.assertEqual(changed_files, ["apps/pc-web/src/index.ts"])

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
