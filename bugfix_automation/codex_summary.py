from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unicodedata

from bugfix_automation.ai_cli import ai_cli_print_command
from bugfix_automation.config import Config
from bugfix_automation.filtering import BugRecord
from bugfix_automation.prompt import PROMPTS_DIR


def branch_name_from_summary(issue_id: str, summary: str) -> str:
    cleaned = sanitize_summary(summary)
    return f"fix/{issue_id}-{cleaned or 'codex-fix'}"


def sanitize_summary(summary: str, max_chars: int = 24) -> str:
    text = unicodedata.normalize("NFKC", summary)
    text = re.sub(r"^fix\([^)]+\):\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\d+\s*[-_]\s*", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[，。；;,.、/\\（）()【】\[\]「」“”\"'：:!！?？\s]+", "", text)
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "", text)
    text = re.sub(r"-+", "-", text).strip(".-_")
    return text[:max_chars]


def generate_codex_change_summary(config: Config, worktree_path: Path, bug: BugRecord, target_app_path: str) -> str:
    diff_stat = _git(worktree_path, ["diff", "--stat", "--", target_app_path])
    changed_files = _git(worktree_path, ["diff", "--name-only", "--", target_app_path])
    diff_sample = _git(worktree_path, ["diff", "--", target_app_path])[-12000:]
    template = (PROMPTS_DIR / "summary.md").read_text(encoding="utf-8").strip()
    prompt = template.format(
        issue_id=bug.issue_id,
        description=bug.description,
        changed_files=changed_files,
        diff_stat=diff_stat,
        diff_sample=diff_sample,
    )
    try:
        result = subprocess.run(
            ai_cli_print_command(config.cli_tool),
            cwd=worktree_path,
            input=prompt,
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return _fallback_summary(changed_files, diff_stat, bug)
    return sanitize_summary(result.stdout.strip().splitlines()[-1]) or _fallback_summary(changed_files, diff_stat, bug)


def _fallback_summary(changed_files: str, diff_stat: str, bug: BugRecord) -> str:
    changed_text = changed_files or diff_stat or bug.description or bug.remark
    if "test" in changed_text.lower():
        return sanitize_summary(f"完善{bug.issue_id}相关测试")
    if "store" in changed_text.lower():
        return sanitize_summary("调整状态管理逻辑")
    return sanitize_summary(bug.description or bug.remark or "前端问题修复")


def _git(path: Path, args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=path, text=True, capture_output=True, check=True)
    return result.stdout.strip()
