import subprocess
import tempfile
import unittest
from pathlib import Path

from bugfix_automation.worktree import commit_all, diff_stat, head_sha, tracked_changed_files


class GitMetadataTest(unittest.TestCase):
    def test_commit_all_returns_commit_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            app = repo / "apps" / "pc-web"
            app.mkdir(parents=True)
            (app / "page.tsx").write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (app / "page.tsx").write_text("after\n", encoding="utf-8")

            changed_files = tracked_changed_files(repo, "apps/pc-web")
            commit = commit_all(repo, "fix: test")
            stat = diff_stat(repo, f"{commit}~1", commit)

        self.assertEqual(changed_files, ["apps/pc-web/page.tsx"])
        self.assertEqual(len(commit), 40)
        self.assertIn("apps/pc-web/page.tsx", stat)

    def test_head_sha_returns_current_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            (repo / "README.md").write_text("x\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, stdout=subprocess.DEVNULL)

            sha = head_sha(repo)

        self.assertEqual(len(sha), 40)


if __name__ == "__main__":
    unittest.main()
