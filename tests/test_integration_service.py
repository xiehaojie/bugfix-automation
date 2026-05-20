"""Tests for the integration queue service."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from bugfix_automation.application import integration_service
from bugfix_automation.config import Config, WorkspaceConfig


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with an initial commit."""
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


def _create_fix_branch_with_commit(repo: Path, branch: str, filename: str, content: str) -> str:
    """Create a fix branch with a commit."""
    subprocess.run(["git", "checkout", "-b", branch], cwd=repo, check=True, capture_output=True)
    file_path = repo / "apps" / "pc-web" / filename
    file_path.write_text(content)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", f"fix: {branch}"], cwd=repo, check=True, capture_output=True)
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True)
    sha = result.stdout.strip()
    subprocess.run(["git", "checkout", "main"], cwd=repo, check=True, capture_output=True)
    return sha


class TestCreateRun:
    def test_creates_run_with_draft_status(self, config: Config):
        data = integration_service.create_run(config, "pc-web", "main", ["fix/bug-1", "fix/bug-2"])
        assert data["status"] == "draft"
        assert data["workspace_id"] == "pc-web"
        assert data["target_branch"] == "main"
        assert len(data["items"]) == 2
        assert data["items"][0]["branch"] == "fix/bug-1"
        assert data["items"][0]["status"] == "pending"

    def test_rejects_empty_branches(self, config: Config):
        with pytest.raises(ValueError, match="至少需要选择一个"):
            integration_service.create_run(config, "pc-web", "main", [])

    def test_rejects_empty_target_branch(self, config: Config):
        with pytest.raises(ValueError, match="必须指定目标分支"):
            integration_service.create_run(config, "pc-web", "", ["fix/bug-1"])

    def test_run_json_persisted(self, config: Config):
        data = integration_service.create_run(config, "pc-web", "main", ["fix/bug-1"])
        loaded = integration_service.get_run(config, data["run_id"])
        assert loaded["run_id"] == data["run_id"]
        assert loaded["status"] == "draft"

    def test_target_branch_slash_does_not_create_nested_run_id(self, config: Config):
        data = integration_service.create_run(config, "pc-web", "feature/demo", ["fix/bug-1"])
        assert "/" not in data["run_id"]
        assert "feature-demo" in data["run_id"]


class TestListRuns:
    def test_empty_when_no_runs(self, config: Config):
        assert integration_service.list_runs(config) == []

    def test_lists_created_runs(self, config: Config):
        integration_service.create_run(config, "pc-web", "main", ["fix/bug-1"])
        runs = integration_service.list_runs(config)
        assert len(runs) == 1
        assert runs[0]["status"] == "draft"


class TestBranchDiscovery:
    def test_available_fix_branches_includes_local_branch_without_worktree(self, config: Config, tmp_repo: Path):
        sha = _create_fix_branch_with_commit(tmp_repo, "fix/bug-local-only", "local.ts", "// local\n")
        branches = integration_service.available_fix_branches(config)
        item = next(branch for branch in branches if branch["branch"] == "fix/bug-local-only")
        assert item["has_worktree"] is False
        assert item["path"] == ""
        assert item["source_commit"] == sha

    def test_available_fix_branches_includes_branch_with_worktree(self, config: Config, tmp_repo: Path):
        sha = _create_fix_branch_with_commit(tmp_repo, "fix/bug-with-worktree", "wt.ts", "// wt\n")
        wt_path = config.worktree_root / "fix-bug-with-worktree"
        wt_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), "fix/bug-with-worktree"],
            cwd=tmp_repo, check=True, capture_output=True,
        )

        branches = integration_service.available_fix_branches(config)
        item = next(branch for branch in branches if branch["branch"] == "fix/bug-with-worktree")
        assert item["has_worktree"] is True
        assert item["path"] == str(wt_path)
        assert item["source_commit"] == sha

    def test_target_branches_excludes_fix_and_integration_branches(self, config: Config, tmp_repo: Path):
        _create_fix_branch_with_commit(tmp_repo, "fix/bug-hidden", "hidden.ts", "// hidden\n")
        subprocess.run(["git", "checkout", "-b", "feature/review"], cwd=tmp_repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "main"], cwd=tmp_repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "integration/tmp"], cwd=tmp_repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "main"], cwd=tmp_repo, check=True, capture_output=True)

        data = integration_service.target_branches(config)
        assert data["current"] == "main"
        assert "main" in data["branches"]
        assert "feature/review" in data["branches"]
        assert "fix/bug-hidden" not in data["branches"]
        assert "integration/tmp" not in data["branches"]


class TestStartRun:
    def test_applies_branch_with_commit(self, config: Config, tmp_repo: Path):
        _create_fix_branch_with_commit(tmp_repo, "fix/bug-1", "fix1.ts", "// fix 1\n")
        data = integration_service.create_run(config, "pc-web", "main", ["fix/bug-1"])
        result = integration_service.start_run(config, data["run_id"])
        assert result["items"][0]["status"] == "applied"
        assert result["items"][0]["apply_method"] == "cherry-pick-no-commit"
        assert result["status"] == "pending-user-approval"

    def test_multiple_branches_applied(self, config: Config, tmp_repo: Path):
        _create_fix_branch_with_commit(tmp_repo, "fix/bug-1", "fix1.ts", "// fix 1\n")
        _create_fix_branch_with_commit(tmp_repo, "fix/bug-2", "fix2.ts", "// fix 2\n")
        data = integration_service.create_run(config, "pc-web", "main", ["fix/bug-1", "fix/bug-2"])
        result = integration_service.start_run(config, data["run_id"])
        assert all(item["status"] == "applied" for item in result["items"])
        assert result["status"] == "pending-user-approval"

    def test_conflict_marks_blocked(self, config: Config, tmp_repo: Path):
        # Create two branches that modify the same file with conflicting content
        subprocess.run(["git", "checkout", "-b", "fix/conflict-1"], cwd=tmp_repo, check=True, capture_output=True)
        (tmp_repo / "apps" / "pc-web" / "index.ts").write_text("// version A\n")
        subprocess.run(["git", "add", "."], cwd=tmp_repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "fix A"], cwd=tmp_repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "main"], cwd=tmp_repo, check=True, capture_output=True)

        subprocess.run(["git", "checkout", "-b", "fix/conflict-2"], cwd=tmp_repo, check=True, capture_output=True)
        (tmp_repo / "apps" / "pc-web" / "index.ts").write_text("// version B\n")
        subprocess.run(["git", "add", "."], cwd=tmp_repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "fix B"], cwd=tmp_repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "main"], cwd=tmp_repo, check=True, capture_output=True)

        data = integration_service.create_run(config, "pc-web", "main", ["fix/conflict-1", "fix/conflict-2"])
        result = integration_service.start_run(config, data["run_id"])
        # First applies, second conflicts
        assert result["items"][0]["status"] == "applied"
        assert result["items"][1]["status"] == "conflict"
        assert result["status"] == "blocked"

    def test_rejects_invalid_status(self, config: Config, tmp_repo: Path):
        _create_fix_branch_with_commit(tmp_repo, "fix/bug-x", "fix_x.ts", "// x\n")
        data = integration_service.create_run(config, "pc-web", "main", ["fix/bug-x"])
        result = integration_service.start_run(config, data["run_id"])
        result = integration_service.confirm_run(config, data["run_id"])
        with pytest.raises(RuntimeError, match="不能开始集成"):
            integration_service.start_run(config, data["run_id"])


class TestConfirmRun:
    def test_creates_final_commit(self, config: Config, tmp_repo: Path):
        _create_fix_branch_with_commit(tmp_repo, "fix/bug-c", "fix_c.ts", "// c\n")
        data = integration_service.create_run(config, "pc-web", "main", ["fix/bug-c"])
        integration_service.start_run(config, data["run_id"])
        result = integration_service.confirm_run(config, data["run_id"])
        assert result["status"] == "committed"
        assert result["final_commit"]
        assert len(result["final_commit"]) == 40

    def test_rejects_when_not_pending(self, config: Config):
        data = integration_service.create_run(config, "pc-web", "main", ["fix/bug-1"])
        with pytest.raises(RuntimeError, match="不能确认提交"):
            integration_service.confirm_run(config, data["run_id"])


class TestCleanupRun:
    def test_deletes_fix_branches(self, config: Config, tmp_repo: Path):
        _create_fix_branch_with_commit(tmp_repo, "fix/bug-clean", "fix_clean.ts", "// clean\n")
        # Create a worktree for the branch (mimics the normal fix flow)
        wt_path = config.worktree_root / "fix-bug-clean"
        wt_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), "fix/bug-clean"],
            cwd=tmp_repo, check=True, capture_output=True,
        )

        data = integration_service.create_run(config, "pc-web", "main", ["fix/bug-clean"])
        integration_service.start_run(config, data["run_id"])
        integration_service.confirm_run(config, data["run_id"])
        result = integration_service.cleanup_run(config, data["run_id"])
        assert result["status"] == "cleaned"
        assert "fix/bug-clean" in result.get("cleaned_branches", [])
        # Branch should be deleted
        rc = subprocess.run(
            ["git", "rev-parse", "--verify", "fix/bug-clean"],
            cwd=tmp_repo, capture_output=True,
        ).returncode
        assert rc != 0

    def test_rejects_when_not_committed(self, config: Config):
        data = integration_service.create_run(config, "pc-web", "main", ["fix/bug-1"])
        with pytest.raises(RuntimeError, match="只有已提交的集成单才能清理"):
            integration_service.cleanup_run(config, data["run_id"])


class TestAbortRun:
    def test_removes_integration_worktree(self, config: Config, tmp_repo: Path):
        _create_fix_branch_with_commit(tmp_repo, "fix/bug-abort", "fix_abort.ts", "// abort\n")
        data = integration_service.create_run(config, "pc-web", "main", ["fix/bug-abort"])
        integration_service.start_run(config, data["run_id"])
        worktree_path = Path(data["integration_worktree"])
        # Worktree should exist after start
        # Now abort
        result = integration_service.abort_run(config, data["run_id"])
        assert result["status"] == "aborted"
        # Fix branch should still exist
        rc = subprocess.run(
            ["git", "rev-parse", "--verify", "fix/bug-abort"],
            cwd=tmp_repo, capture_output=True,
        ).returncode
        assert rc == 0

    def test_rejects_when_already_committed(self, config: Config, tmp_repo: Path):
        _create_fix_branch_with_commit(tmp_repo, "fix/bug-ac", "fix_ac.ts", "// ac\n")
        data = integration_service.create_run(config, "pc-web", "main", ["fix/bug-ac"])
        integration_service.start_run(config, data["run_id"])
        integration_service.confirm_run(config, data["run_id"])
        with pytest.raises(RuntimeError, match="已提交的集成单不能中止"):
            integration_service.abort_run(config, data["run_id"])


class TestDeleteRun:
    def test_deletes_draft_run_record_without_deleting_fix_branch(self, config: Config, tmp_repo: Path):
        _create_fix_branch_with_commit(tmp_repo, "fix/bug-delete-draft", "delete_draft.ts", "// draft\n")
        data = integration_service.create_run(config, "pc-web", "main", ["fix/bug-delete-draft"])
        run_dir = config.runs_root / "integration-runs" / data["run_id"]

        result = integration_service.delete_run(config, data["run_id"])

        assert result == {"run_id": data["run_id"], "deleted": True}
        assert not run_dir.exists()
        rc = subprocess.run(
            ["git", "rev-parse", "--verify", "fix/bug-delete-draft"],
            cwd=tmp_repo, capture_output=True,
        ).returncode
        assert rc == 0

    def test_deletes_aborted_run_record(self, config: Config, tmp_repo: Path):
        _create_fix_branch_with_commit(tmp_repo, "fix/bug-delete-aborted", "delete_aborted.ts", "// aborted\n")
        data = integration_service.create_run(config, "pc-web", "main", ["fix/bug-delete-aborted"])
        integration_service.start_run(config, data["run_id"])
        integration_service.abort_run(config, data["run_id"])

        integration_service.delete_run(config, data["run_id"])

        with pytest.raises(FileNotFoundError):
            integration_service.get_run(config, data["run_id"])

    def test_rejects_running_run(self, config: Config):
        data = integration_service.create_run(config, "pc-web", "main", ["fix/bug-running"])
        loaded = integration_service.get_run(config, data["run_id"])
        loaded["status"] = "running"
        integration_service._save_run(config, data["run_id"], loaded)

        with pytest.raises(RuntimeError, match="正在执行中"):
            integration_service.delete_run(config, data["run_id"])
