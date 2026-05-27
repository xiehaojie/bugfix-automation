from __future__ import annotations

import os
import subprocess
from pathlib import Path


def run(
    command: list[str],
    cwd: Path,
    path_prefix: str | Path | None = None,
    stdin_text: str | None = None,
    log_path: Path | None = None,
) -> None:
    """Run a subprocess, optionally prepending *path_prefix* to ``PATH``.

    When *log_path* is given the command line and combined stdout/stderr are
    appended to that file instead of being printed to the terminal.
    """
    env = os.environ.copy()
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env.get('PATH', '')}"
    if log_path is None:
        subprocess.run(
            command, cwd=cwd, env=env,
            input=stdin_text, text=stdin_text is not None, check=True,
        )
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"\n$ {' '.join(command)}\n")
        log_file.flush()
        subprocess.run(
            command, cwd=cwd, env=env,
            input=stdin_text, text=stdin_text is not None,
            stdout=log_file, stderr=subprocess.STDOUT, check=True,
        )


def git(cwd: Path, args: list[str], *, strip: bool = True) -> str:
    """Run a git command and return stdout.

    When *strip* is ``True`` (default) the output is stripped of leading and
    trailing whitespace.  Set *strip* to ``False`` when the raw output must be
    preserved (e.g. binary diffs passed to ``git apply``).
    """
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True,
    )
    return result.stdout.strip() if strip else result.stdout


def git_rc(cwd: Path, args: list[str], *, strip: bool = True) -> tuple[int, str, str]:
    """Run a git command without raising on failure.

    Returns ``(returncode, stdout, stderr)``.
    When *strip* is ``True`` (default) stdout and stderr are stripped.
    """
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True,
    )
    if strip:
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    return result.returncode, result.stdout, result.stderr


def run_git(cwd: Path, args: list[str]) -> None:
    """Run a git command, discarding output.  Raises on non-zero exit."""
    subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True,
    )


def run_git_quiet(cwd: Path, args: list[str]) -> None:
    """Run a git command, discarding output.  Never raises."""
    subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True,
    )
