from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from bugfix_automation.application import fix_validation_service
from bugfix_automation.config import Config, WorkspaceConfig


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    (repo / "apps" / "pc-web").mkdir(parents=True)
    (repo / "apps" / "pc-web" / "index.ts").write_text("// init\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


@pytest.fixture
def config(tmp_path: Path, tmp_repo: Path) -> Config:
    return Config(
        excel_path=tmp_path / "test.xlsx",
        sheet_name="Sheet1",
        assignee="test",
        target_repo=tmp_repo,
        target_app_path="apps/pc-web",
        worktree_root=tmp_path / ".target-worktrees",
        runs_root=tmp_path / "runs",
        logs_root=tmp_path / "logs",
        data_root=tmp_path / "data",
        storage_db_path=tmp_path / "data" / "app.sqlite3",
        launchd_label="test",
        cli_tool="echo",
        schedule_hour=22,
        schedule_minute=0,
        approval_web_port=8765,
        approval_api_port=8766,
        active_workspace="pc-web",
        workspaces=(
            WorkspaceConfig(
                id="pc-web",
                name="PC Web",
                target_repo=tmp_repo,
                target_app_path="apps/pc-web",
                scope_paths=("apps/pc-web",),
                verify_commands=(),
                prompt_context_paths=(),
                max_concurrency=2,
            ),
        ),
    )


def _create_fix_branch(repo: Path, branch: str, filename: str, content: str) -> str:
    subprocess.run(["git", "checkout", "-b", branch], cwd=repo, check=True, capture_output=True)
    (repo / "apps" / "pc-web" / filename).write_text(content)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", f"fix: {branch}"], cwd=repo, check=True, capture_output=True)
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True)
    subprocess.run(["git", "checkout", "main"], cwd=repo, check=True, capture_output=True)
    return result.stdout.strip()


class TestVerify:
    def test_creates_preview_for_fix_branch(self, config: Config, tmp_repo: Path):
        sha = _create_fix_branch(tmp_repo, "fix/bug-1", "fix1.ts", "// fix 1\n")

        result = fix_validation_service.verify(config, "fix/bug-1")

        assert result["status"] == "ready-to-commit"
        assert result["source_commit"] == sha
        assert result["apply_method"] == "cherry-pick-no-commit"
        assert result["changed_files"] == ["apps/pc-web/fix1.ts"]
        assert Path(result["integration_worktree"]).exists()

    def test_preview_does_not_create_node_modules_or_verify_logs(self, config: Config, tmp_repo: Path):
        _create_fix_branch(tmp_repo, "fix/bug-logs", "logs.ts", "// logs\n")
        source_node_modules = tmp_repo / "apps" / "pc-web" / "node_modules"
        source_node_modules.mkdir()

        result = fix_validation_service.verify(config, "fix/bug-logs")
        worktree_node_modules = Path(result["integration_worktree"]) / "apps" / "pc-web" / "node_modules"

        assert result["status"] == "ready-to-commit"
        assert result["verify"] == {"status": "ai-verified", "commands": []}
        assert not worktree_node_modules.exists()
        assert not list((config.runs_root / "fix-validations").glob("*/ai-verify.log"))

    def test_rejects_non_fix_branch(self, config: Config):
        with pytest.raises(ValueError, match="只能验证"):
            fix_validation_service.verify(config, "feature/demo")

    def test_marks_conflict(self, config: Config, tmp_repo: Path):
        subprocess.run(["git", "checkout", "-b", "feature/base-change"], cwd=tmp_repo, check=True, capture_output=True)
        (tmp_repo / "apps" / "pc-web" / "index.ts").write_text("// base change\n")
        subprocess.run(["git", "add", "."], cwd=tmp_repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "base change"], cwd=tmp_repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "main"], cwd=tmp_repo, check=True, capture_output=True)
        _create_fix_branch(tmp_repo, "fix/conflict", "index.ts", "// fix change\n")
        subprocess.run(["git", "checkout", "feature/base-change"], cwd=tmp_repo, check=True, capture_output=True)

        result = fix_validation_service.verify(config, "fix/conflict")

        assert result["status"] == "conflict"
        assert "cherry-pick" in result["error"]


class TestCommitAndRevert:
    def test_commits_and_reverts_on_integration_branch(self, config: Config, tmp_repo: Path):
        _create_fix_branch(tmp_repo, "fix/bug-commit", "commit.ts", "// commit\n")
        fix_validation_service.verify(config, "fix/bug-commit")

        committed = fix_validation_service.commit_validation(config, "fix/bug-commit", "integration")
        reverted = fix_validation_service.revert_validation(config, "fix/bug-commit")

        assert committed["status"] == "committed"
        assert committed["final_commit_location"] == "integration"
        assert len(committed["final_commit"]) == 40
        assert reverted["status"] == "reverted"
        assert len(reverted["revert_commit"]) == 40

    def test_commits_to_target_when_requested(self, config: Config, tmp_repo: Path):
        _create_fix_branch(tmp_repo, "fix/bug-target", "target.ts", "// target\n")
        fix_validation_service.verify(config, "fix/bug-target")

        result = fix_validation_service.commit_validation(config, "fix/bug-target", "target")

        assert result["status"] == "committed"
        assert result["final_commit_location"] == "target"
        assert (tmp_repo / "apps" / "pc-web" / "target.ts").read_text() == "// target\n"

    def test_rejects_invalid_commit_location(self, config: Config):
        with pytest.raises(ValueError, match="提交位置"):
            fix_validation_service.commit_validation(config, "fix/missing", "main")


class TestPreviewAndCleanup:
    def test_remove_preview_keeps_fix_branch(self, config: Config, tmp_repo: Path):
        _create_fix_branch(tmp_repo, "fix/bug-preview", "preview.ts", "// preview\n")
        verified = fix_validation_service.verify(config, "fix/bug-preview")

        result = fix_validation_service.remove_preview(config, "fix/bug-preview")
        branch_rc = subprocess.run(["git", "rev-parse", "--verify", "fix/bug-preview"], cwd=tmp_repo, capture_output=True).returncode

        assert result["status"] == "preview-removed"
        assert not Path(verified["integration_worktree"]).exists()
        assert branch_rc == 0

    def test_cleanup_source_deletes_fix_branch_after_commit(self, config: Config, tmp_repo: Path):
        _create_fix_branch(tmp_repo, "fix/bug-clean", "clean.ts", "// clean\n")
        wt_path = config.worktree_root / "fix-bug-clean"
        wt_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "worktree", "add", str(wt_path), "fix/bug-clean"], cwd=tmp_repo, check=True, capture_output=True)
        fix_validation_service.verify(config, "fix/bug-clean")
        fix_validation_service.commit_validation(config, "fix/bug-clean", "integration")

        result = fix_validation_service.cleanup_source(config, "fix/bug-clean")
        branch_rc = subprocess.run(["git", "rev-parse", "--verify", "fix/bug-clean"], cwd=tmp_repo, capture_output=True).returncode

        assert result["status"] == "cleaned"
        assert result["cleaned_branch"] == "fix/bug-clean"
        assert branch_rc != 0
