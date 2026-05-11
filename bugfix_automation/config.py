from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Config:
    excel_path: Path
    sheet_name: str
    assignee: str
    target_repo: Path
    target_app_path: str
    worktree_root: Path
    runs_root: Path
    logs_root: Path
    launchd_label: str
    codex_bin: str


def load_config() -> Config:
    repo_root = Path(__file__).resolve().parents[1]
    target_repo = Path(os.environ.get("BUGFIX_TARGET_REPO", "/Users/xiehaojie/code/monorepo")).expanduser()
    return Config(
        excel_path=Path(os.environ.get("BUGFIX_EXCEL_PATH", "/Users/xiehaojie/Desktop/亦城数智人在线清单.xlsx")).expanduser(),
        sheet_name=os.environ.get("BUGFIX_SHEET_NAME", "在线问题清单"),
        assignee=os.environ.get("BUGFIX_ASSIGNEE", "谢浩杰"),
        target_repo=target_repo,
        target_app_path=os.environ.get("BUGFIX_TARGET_APP_PATH", "apps/pc-web"),
        worktree_root=Path(os.environ.get("BUGFIX_WORKTREE_ROOT", str(repo_root / ".target-worktrees"))).expanduser(),
        runs_root=Path(os.environ.get("BUGFIX_RUNS_ROOT", str(repo_root / "runs"))).expanduser(),
        logs_root=Path(os.environ.get("BUGFIX_LOGS_ROOT", str(repo_root / "logs"))).expanduser(),
        launchd_label=os.environ.get("BUGFIX_LAUNCHD_LABEL", "local.bugfix-automation.nightly"),
        codex_bin=os.environ.get("BUGFIX_CODEX_BIN", "codex"),
    )
