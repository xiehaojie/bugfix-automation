# Capability System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace weak local workflow prompts with a thin capability adapter that connects Codex to Superpowers and Claude Code to `everything-claude-code`.

**Architecture:** Add `CapabilitySystemConfig` to runtime config, then introduce `bugfix_automation/capability_system.py` as the single boundary for provider resolution, capability status, ECC artifact installation, and prompt contract rendering. Keep existing runner/prompt APIs compatible while making prompt templates consume a `{capability_contract}` instead of duplicating TDD/review/verification methodology.

**Tech Stack:** Python 3 dataclasses, pathlib/shutil, unittest, FastAPI config payloads, Next.js/TypeScript display-only UI, local Superpowers/ECC filesystem artifacts.

---

## File Structure

- Create `bugfix_automation/capability_system.py`: provider resolution, status, install, prompt contract rendering.
- Modify `bugfix_automation/config.py`: add capability dataclasses, defaults, YAML/SQLite merge parsing.
- Modify `bugfix_automation/worktree.py`: delegate provider-native artifact installation or keep legacy helpers narrowly scoped.
- Modify `bugfix_automation/runner.py`: install capabilities before rendering/running prompt and include status in AI session/log metadata.
- Modify `bugfix_automation/approval.py`: install capabilities during rework before invoking the AI CLI.
- Modify `bugfix_automation/prompt.py`: pass `capability_contract` into templates.
- Modify `prompts/fix_frontend.md`, `prompts/fix_backend.md`, `prompts/fix_fullstack.md`, `prompts/rework.md`: remove local workflow imitation and insert `{capability_contract}`.
- Modify `bugfix_automation/application/config_service.py`: expose read-only `capability_status`.
- Modify `approval-web/src/features/approval/types.ts`: add capability status types.
- Modify `approval-web/app/page.tsx`: show current capability provider/source/warnings in the AI tool config area.
- Modify tests:
  - `tests/test_config.py`
  - `tests/test_filtering_prompt_report.py`
  - `tests/test_worktree.py`
  - `tests/test_approval.py`
  - `tests/test_fastapi_api.py`

---

### Task 1: Config Model for Capability System

**Files:**
- Modify: `bugfix_automation/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing YAML config test**

Add this test to `tests/test_config.py`:

```python
def test_load_config_parses_capability_system_from_yaml(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config.yaml"
        ecc_root = root / "everything-claude-code"
        config_path.write_text(
            f"""
storage_db_path: {root / "data" / "app.sqlite3"}
cli_tool: claude
capability_system:
  provider: auto
  strict: true
  codex:
    source: superpowers
    required_skills: superpowers:test-driven-development,superpowers:verification-before-completion
  claude:
    source: {ecc_root}
    required_agents: planner,code-reviewer
    optional_agents: security-reviewer
    required_skills: tdd-workflow,verification-loop
""",
            encoding="utf-8",
        )

        config = load_config(config_path)

    self.assertEqual(config.capability_system.provider, "auto")
    self.assertTrue(config.capability_system.strict)
    self.assertEqual(config.capability_system.codex.source, "superpowers")
    self.assertEqual(
        config.capability_system.codex.required_skills,
        ("superpowers:test-driven-development", "superpowers:verification-before-completion"),
    )
    self.assertEqual(config.capability_system.claude.source, str(ecc_root))
    self.assertEqual(config.capability_system.claude.required_agents, ("planner", "code-reviewer"))
    self.assertEqual(config.capability_system.claude.optional_agents, ("security-reviewer",))
    self.assertEqual(config.capability_system.claude.required_skills, ("tdd-workflow", "verification-loop"))
```

- [ ] **Step 2: Run test to verify failure**

Run: `python3 -m unittest tests.test_config.ConfigTest.test_load_config_parses_capability_system_from_yaml`

Expected: FAIL with `AttributeError: 'Config' object has no attribute 'capability_system'`.

- [ ] **Step 3: Add config dataclasses**

In `bugfix_automation/config.py`, after `ExcelProfile`, add:

```python
@dataclass(frozen=True)
class CapabilityProviderConfig:
    source: str = ""
    required_agents: tuple[str, ...] = ()
    optional_agents: tuple[str, ...] = ()
    required_skills: tuple[str, ...] = ()
    optional_skills: tuple[str, ...] = ()


@dataclass(frozen=True)
class CapabilitySystemConfig:
    provider: str = "auto"
    strict: bool = False
    codex: CapabilityProviderConfig = field(
        default_factory=lambda: CapabilityProviderConfig(
            source="superpowers",
            required_skills=(
                "superpowers:using-superpowers",
                "superpowers:test-driven-development",
                "superpowers:systematic-debugging",
                "superpowers:verification-before-completion",
                "superpowers:requesting-code-review",
            ),
            optional_skills=("superpowers:subagent-driven-development",),
        )
    )
    claude: CapabilityProviderConfig = field(
        default_factory=lambda: CapabilityProviderConfig(
            source="/Users/xiehaojie/code/everything-claude-code",
            required_agents=(
                "planner",
                "architect",
                "tdd-guide",
                "code-reviewer",
                "typescript-reviewer",
                "build-error-resolver",
            ),
            optional_agents=("security-reviewer", "performance-optimizer"),
            required_skills=("tdd-workflow", "coding-standards", "verification-loop"),
        )
    )
```

Add this field to `Config`:

```python
capability_system: CapabilitySystemConfig = CapabilitySystemConfig()
```

- [ ] **Step 4: Add parser helper**

In `bugfix_automation/config.py`, near `_excel_profile`, add:

```python
def _capability_system(value: Any) -> CapabilitySystemConfig:
    if not isinstance(value, dict):
        return CapabilitySystemConfig()
    return CapabilitySystemConfig(
        provider=str(value.get("provider", "auto")).strip() or "auto",
        strict=bool(value.get("strict", False)),
        codex=_capability_provider(
            value.get("codex"),
            CapabilitySystemConfig().codex,
        ),
        claude=_capability_provider(
            value.get("claude"),
            CapabilitySystemConfig().claude,
        ),
    )


def _capability_provider(value: Any, default: CapabilityProviderConfig) -> CapabilityProviderConfig:
    if not isinstance(value, dict):
        return default
    return CapabilityProviderConfig(
        source=str(value.get("source", default.source)).strip() or default.source,
        required_agents=_string_tuple(value.get("required_agents"), default.required_agents),
        optional_agents=_string_tuple(value.get("optional_agents"), default.optional_agents),
        required_skills=_string_tuple(value.get("required_skills"), default.required_skills),
        optional_skills=_string_tuple(value.get("optional_skills"), default.optional_skills),
    )
```

In `load_config`, pass:

```python
capability_system=_capability_system(yaml_values.get("capability_system")),
```

- [ ] **Step 5: Run config test**

Run: `python3 -m unittest tests.test_config.ConfigTest.test_load_config_parses_capability_system_from_yaml`

Expected: PASS.

- [ ] **Step 6: Write failing SQLite merge test**

Add this test to `tests/test_config.py`:

```python
def test_load_config_merges_capability_system_from_sqlite(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config.yaml"
        db_path = root / "data" / "app.sqlite3"
        config_path.write_text(
            f"""
storage_db_path: {db_path}
cli_tool: codex
capability_system:
  provider: auto
  claude:
    source: /tmp/from-yaml
""",
            encoding="utf-8",
        )
        set_setting(
            db_path,
            "capability_system",
            {
                "provider": "claude",
                "strict": True,
                "claude": {
                    "source": "/tmp/from-sqlite",
                    "required_agents": ["planner"],
                    "required_skills": ["tdd-workflow"],
                },
            },
        )

        config = load_config(config_path)

    self.assertEqual(config.capability_system.provider, "claude")
    self.assertTrue(config.capability_system.strict)
    self.assertEqual(config.capability_system.claude.source, "/tmp/from-sqlite")
    self.assertEqual(config.capability_system.claude.required_agents, ("planner",))
    self.assertEqual(config.capability_system.claude.required_skills, ("tdd-workflow",))
```

- [ ] **Step 7: Run SQLite merge test to verify failure**

Run: `python3 -m unittest tests.test_config.ConfigTest.test_load_config_merges_capability_system_from_sqlite`

Expected: FAIL because `_merge_runtime_settings` does not merge `capability_system`.

- [ ] **Step 8: Merge SQLite capability settings**

In `_merge_runtime_settings`, add:

```python
if "capability_system" in sqlite_settings:
    merged["capability_system"] = sqlite_settings["capability_system"]
```

- [ ] **Step 9: Run config tests**

Run: `python3 -m unittest tests.test_config`

Expected: PASS.

---

### Task 2: Capability Provider Resolution and Status

**Files:**
- Create: `bugfix_automation/capability_system.py`
- Test: `tests/test_filtering_prompt_report.py`

- [ ] **Step 1: Write failing provider resolution tests**

Add imports in `tests/test_filtering_prompt_report.py`:

```python
from dataclasses import replace
from bugfix_automation.capability_system import capability_status, render_capability_contract, resolve_capability_provider
from bugfix_automation.config import CapabilityProviderConfig, CapabilitySystemConfig
```

Add tests:

```python
def test_capability_provider_auto_follows_cli_tool(self) -> None:
    base = Config(
        excel_path=Path("/tmp/bugs.xlsx"),
        sheet_name="Sheet1",
        assignee="谢浩杰",
        target_repo=Path("/tmp/repo"),
        target_app_path="apps/pc-web",
        worktree_root=Path("/tmp/worktrees"),
        runs_root=Path("/tmp/runs"),
        logs_root=Path("/tmp/logs"),
        launchd_label="local.test",
        cli_tool="claude",
        schedule_hour=22,
        schedule_minute=0,
        approval_web_port=8765,
        approval_api_port=8766,
    )

    self.assertEqual(resolve_capability_provider(base), "claude")
    self.assertEqual(resolve_capability_provider(replace(base, cli_tool="codex")), "codex")


def test_capability_provider_explicit_config_wins(self) -> None:
    config = Config(
        excel_path=Path("/tmp/bugs.xlsx"),
        sheet_name="Sheet1",
        assignee="谢浩杰",
        target_repo=Path("/tmp/repo"),
        target_app_path="apps/pc-web",
        worktree_root=Path("/tmp/worktrees"),
        runs_root=Path("/tmp/runs"),
        logs_root=Path("/tmp/logs"),
        launchd_label="local.test",
        cli_tool="codex",
        schedule_hour=22,
        schedule_minute=0,
        approval_web_port=8765,
        approval_api_port=8766,
        capability_system=CapabilitySystemConfig(provider="claude"),
    )

    self.assertEqual(resolve_capability_provider(config), "claude")
```

- [ ] **Step 2: Run provider tests to verify failure**

Run: `python3 -m unittest tests.test_filtering_prompt_report.FilteringPromptReportTest.test_capability_provider_auto_follows_cli_tool tests.test_filtering_prompt_report.FilteringPromptReportTest.test_capability_provider_explicit_config_wins`

Expected: FAIL with `ModuleNotFoundError: No module named 'bugfix_automation.capability_system'`.

- [ ] **Step 3: Implement provider resolution and status**

Create `bugfix_automation/capability_system.py`:

```python
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from bugfix_automation.ai_cli import ai_cli_kind
from bugfix_automation.config import CapabilityProviderConfig, Config


def resolve_capability_provider(config: Config) -> str:
    provider = config.capability_system.provider.strip().lower()
    if provider in {"codex", "claude"}:
        return provider
    kind = ai_cli_kind(config.cli_tool)
    return "claude" if kind == "claude" else "codex"


def active_provider_config(config: Config) -> CapabilityProviderConfig:
    provider = resolve_capability_provider(config)
    return config.capability_system.claude if provider == "claude" else config.capability_system.codex


def capability_status(config: Config) -> dict[str, Any]:
    provider = resolve_capability_provider(config)
    provider_config = active_provider_config(config)
    if provider == "claude":
        return _claude_status(provider_config)
    return _codex_status(provider_config)


def _claude_status(provider_config: CapabilityProviderConfig) -> dict[str, Any]:
    source = Path(provider_config.source).expanduser()
    required_agents = [_artifact_status(name, source / "agents" / f"{name}.md") for name in provider_config.required_agents]
    optional_agents = [_artifact_status(name, source / "agents" / f"{name}.md") for name in provider_config.optional_agents]
    required_skills = [_artifact_status(name, source / "skills" / name) for name in provider_config.required_skills]
    optional_skills = [_artifact_status(name, source / "skills" / name) for name in provider_config.optional_skills]
    warnings = [
        f"Missing required Claude agent: {item['name']}"
        for item in required_agents
        if not item["available"]
    ] + [
        f"Missing required Claude skill: {item['name']}"
        for item in required_skills
        if not item["available"]
    ]
    return {
        "provider": "claude",
        "source": str(source),
        "required": {"agents": required_agents, "skills": required_skills},
        "optional": {"agents": optional_agents, "skills": optional_skills},
        "warnings": warnings,
    }


def _codex_status(provider_config: CapabilityProviderConfig) -> dict[str, Any]:
    required_skills = [{"name": name, "available": _superpower_skill_available(name)} for name in provider_config.required_skills]
    optional_skills = [{"name": name, "available": _superpower_skill_available(name)} for name in provider_config.optional_skills]
    warnings = [
        f"Superpowers skill not detected locally: {item['name']}"
        for item in required_skills
        if not item["available"]
    ]
    return {
        "provider": "codex",
        "source": provider_config.source,
        "required": {"agents": [], "skills": required_skills},
        "optional": {"agents": [], "skills": optional_skills},
        "warnings": warnings,
    }


def _artifact_status(name: str, path: Path) -> dict[str, Any]:
    return {"name": name, "path": str(path), "available": path.exists()}


def _superpower_skill_available(skill_name: str) -> bool:
    local_name = skill_name.split(":", 1)[-1]
    roots = (
        Path.home() / ".codex" / "plugins" / "cache" / "claude-plugins-official" / "superpowers",
        Path.home() / ".codex" / "plugins" / "cache" / "openai-curated" / "superpowers",
    )
    for root in roots:
        if not root.exists():
            continue
        if any(root.glob(f"**/skills/{local_name}/SKILL.md")):
            return True
    return False
```

- [ ] **Step 4: Run provider tests**

Run: `python3 -m unittest tests.test_filtering_prompt_report.FilteringPromptReportTest.test_capability_provider_auto_follows_cli_tool tests.test_filtering_prompt_report.FilteringPromptReportTest.test_capability_provider_explicit_config_wins`

Expected: PASS.

- [ ] **Step 5: Write failing status and contract tests**

Add:

```python
def test_claude_capability_status_reports_missing_required_artifacts(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "ecc"
        (source / "agents").mkdir(parents=True)
        (source / "agents" / "planner.md").write_text("---\nname: planner\n---\n", encoding="utf-8")
        config = Config(
            excel_path=Path("/tmp/bugs.xlsx"),
            sheet_name="Sheet1",
            assignee="谢浩杰",
            target_repo=Path("/tmp/repo"),
            target_app_path="apps/pc-web",
            worktree_root=Path("/tmp/worktrees"),
            runs_root=Path("/tmp/runs"),
            logs_root=Path("/tmp/logs"),
            launchd_label="local.test",
            cli_tool="claude",
            schedule_hour=22,
            schedule_minute=0,
            approval_web_port=8765,
            approval_api_port=8766,
            capability_system=CapabilitySystemConfig(
                claude=CapabilityProviderConfig(
                    source=str(source),
                    required_agents=("planner", "code-reviewer"),
                    required_skills=("tdd-workflow",),
                )
            ),
        )

        status = capability_status(config)

    self.assertEqual(status["provider"], "claude")
    self.assertIn("Missing required Claude agent: code-reviewer", status["warnings"])
    self.assertIn("Missing required Claude skill: tdd-workflow", status["warnings"])


def test_capability_contract_mentions_provider_native_capabilities(self) -> None:
    codex_config = Config(
        excel_path=Path("/tmp/bugs.xlsx"),
        sheet_name="Sheet1",
        assignee="谢浩杰",
        target_repo=Path("/tmp/repo"),
        target_app_path="apps/pc-web",
        worktree_root=Path("/tmp/worktrees"),
        runs_root=Path("/tmp/runs"),
        logs_root=Path("/tmp/logs"),
        launchd_label="local.test",
        cli_tool="codex",
        schedule_hour=22,
        schedule_minute=0,
        approval_web_port=8765,
        approval_api_port=8766,
        capability_system=CapabilitySystemConfig(
            codex=CapabilityProviderConfig(
                source="superpowers",
                required_skills=("superpowers:test-driven-development",),
            )
        ),
    )
    claude_config = replace(
        codex_config,
        cli_tool="claude",
        capability_system=CapabilitySystemConfig(
            claude=CapabilityProviderConfig(
                source="/tmp/ecc",
                required_agents=("planner", "code-reviewer"),
                required_skills=("tdd-workflow",),
            )
        ),
    )

    self.assertIn("Codex + Superpowers", render_capability_contract(codex_config))
    self.assertIn("superpowers:test-driven-development", render_capability_contract(codex_config))
    self.assertIn("Claude Code + everything-claude-code", render_capability_contract(claude_config))
    self.assertIn("planner, code-reviewer", render_capability_contract(claude_config))
    self.assertIn("tdd-workflow", render_capability_contract(claude_config))
```

- [ ] **Step 6: Run status and contract tests to verify failure**

Run: `python3 -m unittest tests.test_filtering_prompt_report.FilteringPromptReportTest.test_claude_capability_status_reports_missing_required_artifacts tests.test_filtering_prompt_report.FilteringPromptReportTest.test_capability_contract_mentions_provider_native_capabilities`

Expected: status test PASS after Step 3; contract test FAIL with missing `render_capability_contract`.

- [ ] **Step 7: Implement contract rendering**

Append to `bugfix_automation/capability_system.py`:

```python
def render_capability_contract(config: Config) -> str:
    provider = resolve_capability_provider(config)
    provider_config = active_provider_config(config)
    status = capability_status(config)
    warnings = "\n".join(f"- {warning}" for warning in status["warnings"]) or "- None detected"
    if provider == "claude":
        agents = ", ".join((*provider_config.required_agents, *provider_config.optional_agents)) or "none configured"
        skills = ", ".join((*provider_config.required_skills, *provider_config.optional_skills)) or "none configured"
        return (
            "Capability system: Claude Code + everything-claude-code\n\n"
            "Use the project-local ECC agents and skills installed under .claude/ when available.\n"
            f"Relevant agents: {agents}\n"
            f"Relevant skills: {skills}\n\n"
            "Do not imitate those workflows manually when an installed agent or skill is available.\n"
            "If a required artifact is unavailable, state that clearly in the final report.\n\n"
            f"Capability warnings:\n{warnings}"
        )
    skills = ", ".join((*provider_config.required_skills, *provider_config.optional_skills)) or "none configured"
    return (
        "Capability system: Codex + Superpowers\n\n"
        "Use the installed Superpowers skills when applicable.\n"
        f"Relevant skills: {skills}\n\n"
        "Do not replace those workflows with a local approximation.\n"
        "If a required skill is unavailable, state that clearly in the final report.\n\n"
        f"Capability warnings:\n{warnings}"
    )
```

- [ ] **Step 8: Run capability tests**

Run: `python3 -m unittest tests.test_filtering_prompt_report.FilteringPromptReportTest.test_capability_provider_auto_follows_cli_tool tests.test_filtering_prompt_report.FilteringPromptReportTest.test_capability_provider_explicit_config_wins tests.test_filtering_prompt_report.FilteringPromptReportTest.test_claude_capability_status_reports_missing_required_artifacts tests.test_filtering_prompt_report.FilteringPromptReportTest.test_capability_contract_mentions_provider_native_capabilities`

Expected: PASS.

---

### Task 3: Claude ECC Artifact Installation

**Files:**
- Modify: `bugfix_automation/capability_system.py`
- Modify: `bugfix_automation/worktree.py`
- Test: `tests/test_worktree.py`

- [ ] **Step 1: Write failing Claude install test**

Add import to `tests/test_worktree.py`:

```python
from bugfix_automation.capability_system import install_capabilities
from bugfix_automation.config import CapabilityProviderConfig, CapabilitySystemConfig, Config
```

Add helper:

```python
def _capability_test_config(source: Path) -> Config:
    return Config(
        excel_path=Path("/tmp/bugs.xlsx"),
        sheet_name="Sheet1",
        assignee="谢浩杰",
        target_repo=Path("/tmp/repo"),
        target_app_path="apps/pc-web",
        worktree_root=Path("/tmp/worktrees"),
        runs_root=Path("/tmp/runs"),
        logs_root=Path("/tmp/logs"),
        launchd_label="local.test",
        cli_tool="claude",
        schedule_hour=22,
        schedule_minute=0,
        approval_web_port=8765,
        approval_api_port=8766,
        capability_system=CapabilitySystemConfig(
            claude=CapabilityProviderConfig(
                source=str(source),
                required_agents=("planner", "code-reviewer"),
                optional_agents=("security-reviewer",),
                required_skills=("tdd-workflow",),
            )
        ),
    )
```

Add test:

```python
def test_install_capabilities_copies_configured_claude_ecc_artifacts(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "everything-claude-code"
        worktree = root / "worktree"
        worktree.mkdir()
        (source / "agents").mkdir(parents=True)
        (source / "skills" / "tdd-workflow").mkdir(parents=True)
        (source / "agents" / "planner.md").write_text("---\nname: planner\n---\nPlanner", encoding="utf-8")
        (source / "agents" / "code-reviewer.md").write_text("---\nname: code-reviewer\n---\nReviewer", encoding="utf-8")
        (source / "skills" / "tdd-workflow" / "SKILL.md").write_text("---\nname: tdd-workflow\n---\nTDD", encoding="utf-8")

        result = install_capabilities(_capability_test_config(source), worktree, root / "automation")

        self.assertTrue((worktree / ".claude" / "agents" / "planner.md").exists())
        self.assertTrue((worktree / ".claude" / "agents" / "code-reviewer.md").exists())
        self.assertTrue((worktree / ".claude" / "skills" / "tdd-workflow" / "SKILL.md").exists())
        self.assertFalse((worktree / ".claude" / "agents" / "security-reviewer.md").exists())
        self.assertIn("Missing optional Claude agent: security-reviewer", result["warnings"])
```

- [ ] **Step 2: Run install test to verify failure**

Run: `python3 -m unittest tests.test_worktree.WorktreeTest.test_install_capabilities_copies_configured_claude_ecc_artifacts`

Expected: FAIL with missing `install_capabilities`.

- [ ] **Step 3: Implement artifact installation**

Append to `bugfix_automation/capability_system.py`:

```python
def install_capabilities(config: Config, worktree_path: Path, automation_repo: Path) -> dict[str, Any]:
    provider = resolve_capability_provider(config)
    if provider == "claude":
        return _install_claude_capabilities(config, worktree_path)
    return capability_status(config)


def _install_claude_capabilities(config: Config, worktree_path: Path) -> dict[str, Any]:
    provider_config = config.capability_system.claude
    source = Path(provider_config.source).expanduser()
    warnings: list[str] = []
    copied_agents: list[str] = []
    copied_skills: list[str] = []
    for name in provider_config.required_agents:
        if _copy_agent(source, worktree_path, name):
            copied_agents.append(name)
        else:
            warnings.append(f"Missing required Claude agent: {name}")
    for name in provider_config.optional_agents:
        if _copy_agent(source, worktree_path, name):
            copied_agents.append(name)
        else:
            warnings.append(f"Missing optional Claude agent: {name}")
    for name in provider_config.required_skills:
        if _copy_skill(source, worktree_path, name):
            copied_skills.append(name)
        else:
            warnings.append(f"Missing required Claude skill: {name}")
    for name in provider_config.optional_skills:
        if _copy_skill(source, worktree_path, name):
            copied_skills.append(name)
        else:
            warnings.append(f"Missing optional Claude skill: {name}")
    return {
        "provider": "claude",
        "source": str(source),
        "copied_agents": copied_agents,
        "copied_skills": copied_skills,
        "warnings": warnings,
    }


def _copy_agent(source: Path, worktree_path: Path, name: str) -> bool:
    src = source / "agents" / f"{name}.md"
    if not src.exists():
        return False
    dst = worktree_path / ".claude" / "agents" / f"{name}.md"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _copy_skill(source: Path, worktree_path: Path, name: str) -> bool:
    src = source / "skills" / name
    if not src.exists():
        return False
    dst = worktree_path / ".claude" / "skills" / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return True
```

- [ ] **Step 4: Run install test**

Run: `python3 -m unittest tests.test_worktree.WorktreeTest.test_install_capabilities_copies_configured_claude_ecc_artifacts`

Expected: PASS.

- [ ] **Step 5: Write failing ignore test for `.claude/skills`**

Extend `test_node_modules_symlink_is_available_but_ignored_by_changed_files` or add:

```python
def test_claude_capability_files_are_ignored_by_scope_checks(self) -> None:
    changed = [
        "apps/pc-web/src/app/page.tsx",
        ".claude/agents/planner.md",
        ".claude/skills/tdd-workflow/SKILL.md",
        ".codex/agents/frontend-fix-agent.toml",
        "apps/server/src/main.java",
    ]

    self.assertEqual(out_of_scope_paths(changed, "apps/pc-web"), ["apps/server/src/main.java"])
```

Ensure `out_of_scope_paths` is imported in `tests/test_worktree.py`.

- [ ] **Step 6: Run ignore test**

Run: `python3 -m unittest tests.test_worktree.WorktreeTest.test_claude_capability_files_are_ignored_by_scope_checks`

Expected: PASS when `.claude/...` paths are already ignored; FAIL with `.claude/...` paths included when ignore prefixes still need the Step 7 change.

- [ ] **Step 7: Update ignore prefixes if test fails**

In `bugfix_automation/worktree.py`, ensure automation prefixes include `.claude/` in:

```python
automation_prefixes = (".codex/", ".claude/", ".bugfix-automation-bin/")
allowed_automation_paths = (".codex/", ".claude/", ".bugfix-automation-bin/")
```

Also ensure `write_worktree_exclude` writes:

```python
if ".claude" not in existing:
    entries += ".claude\n"
```

- [ ] **Step 8: Run worktree tests**

Run: `python3 -m unittest tests.test_worktree`

Expected: PASS.

---

### Task 4: Prompt Contract Integration

**Files:**
- Modify: `bugfix_automation/prompt.py`
- Modify: `prompts/fix_frontend.md`
- Modify: `prompts/fix_backend.md`
- Modify: `prompts/fix_fullstack.md`
- Test: `tests/test_filtering_prompt_report.py`

- [ ] **Step 1: Write failing prompt test**

Add:

```python
def test_prompt_uses_capability_contract_instead_of_local_agent_workflow(self) -> None:
    bug = filter_bugs([
        {
            "_excel_row": "2",
            "序号": "87",
            "提出人状态": "处理中",
            "来源系统": "小亦PC",
            "对接人": "谢浩杰",
            "对接人状态": "",
            "问题描述": "账号离线状态",
        }
    ], assignee="谢浩杰")[0]

    prompt = render_codex_prompt(
        bug,
        target_app_path="apps/pc-web",
        capability_contract="Capability system: Claude Code + everything-claude-code\nUse ECC.",
        ai_tool_label="Claude Code",
    )

    self.assertIn("Capability system: Claude Code + everything-claude-code", prompt)
    self.assertIn("账号离线状态", prompt)
    self.assertIn("不要 push", prompt)
    self.assertNotIn("先委派 bug-triage-agent", prompt)
    self.assertNotIn("再委派 frontend-fix-agent", prompt)
```

- [ ] **Step 2: Run prompt test to verify failure**

Run: `python3 -m unittest tests.test_filtering_prompt_report.FilteringPromptReportTest.test_prompt_uses_capability_contract_instead_of_local_agent_workflow`

Expected: FAIL because `render_codex_prompt` does not accept `capability_contract` or templates still contain old workflow wording.

- [ ] **Step 3: Add `capability_contract` parameter**

In `bugfix_automation/prompt.py`, update signature:

```python
def render_codex_prompt(
    bug: BugRecord,
    target_app_path: str,
    prompt_fields: tuple[str, ...] | None = None,
    prompt_template: str = "",
    context_paths: tuple[str, ...] | None = None,
    workspace_name: str = "",
    image_paths: list[Path] | None = None,
    scope: str = "frontend",
    ai_tool_label: str = "Codex",
    capability_contract: str = "",
) -> str:
```

Pass to `.format`:

```python
capability_contract=capability_contract or "Capability system: not configured",
```

- [ ] **Step 4: Rewrite fix templates around thin business context**

Replace `prompts/fix_frontend.md` with:

```markdown
你是本地自动化流程启动的 {ai_tool_label}。请处理这个前端 bug 修复任务。

能力系统：
{capability_contract}

任务目标：
- 根据 Excel bug 信息定位并修复问题。
- 只修改 `{target_app_path}` 及其前端相关测试/配置。
- 如果判断该 bug 需要后端、数据、部署或移动端修改，请停止并在最终报告中说明。

硬性约束：
- 不要修改后端、接口服务、数据库迁移或部署配置。
- 不要 push 到任何远端仓库。
- 不要自动 git commit；等待用户在审批台确认后再提交。
- 不要使用破坏性 git 命令。
- 修复后运行项目可用的 lint/build/test 验证；如果无法运行，请说明原因。

Excel 信息：
- Excel 行号: {excel_row}
- 序号: {issue_id}
- 工作区: {workspace_name}

配置提示词：
{prompt_template}

Excel 选中字段：
{selected_lines}

原始 Excel 行完整信息：
{raw_lines}

随本次 {ai_tool_label} 调用传入的截图：
{image_lines}

需要优先阅读的工程文件/目录：
{context_lines}

最终输出要求：
- 修改了哪些文件。
- 运行了哪些验证命令及结果。
- 是否存在未解决风险。
- 如果未修改代码，说明原因。
```

Replace backend/fullstack templates with the same structure, changing only the task target and scope constraints:

Backend task target:

```markdown
- 只修改 `{target_app_path}` 及其后端相关测试/配置。
- 不要修改前端代码、UI 组件或样式文件。
```

Fullstack task target:

```markdown
- 只修改 `{target_app_path}` 范围内的代码和配置。
- 谨慎处理数据库迁移；如需 schema 变更请在最终报告中详细说明。
```

- [ ] **Step 5: Run prompt tests**

Run: `python3 -m unittest tests.test_filtering_prompt_report`

Expected: FAIL for existing assertions that require old agent names. Replace those assertions with checks for the capability contract and preserved hard constraints:

```python
self.assertIn("能力系统", prompt)
self.assertIn("不要 push", prompt)
self.assertIn("不要自动 git commit", prompt)
self.assertIn("apps/pc-web", prompt)
```

- [ ] **Step 6: Run prompt tests again**

Run: `python3 -m unittest tests.test_filtering_prompt_report`

Expected: PASS.

---

### Task 5: Runner and Rework Wiring

**Files:**
- Modify: `bugfix_automation/runner.py`
- Modify: `bugfix_automation/approval.py`
- Test: `tests/test_approval.py`

- [ ] **Step 1: Write failing runner prompt wiring test**

Add this import to `tests/test_approval.py`:

```python
from bugfix_automation.runner import codex_log_path, process_bug
```

Add this test to `tests/test_approval.py`:

```python
def test_process_bug_installs_capabilities_before_running_ai(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        worktree = root / "worktree"
        worktree.mkdir()
        wrapper = root / "wrapper"
        wrapper.mkdir()
        config = Config(
            excel_path=root / "bugs.xlsx",
            sheet_name="Sheet1",
            assignee="谢浩杰",
            target_repo=root / "repo",
            target_app_path="apps/pc-web",
            worktree_root=root / "worktrees",
            runs_root=root / "runs",
            logs_root=root / "logs",
            data_root=root / "data",
            storage_db_path=root / "data" / "app.sqlite3",
            launchd_label="local.test",
            cli_tool="claude",
            schedule_hour=22,
            schedule_minute=0,
            approval_web_port=8765,
            approval_api_port=8766,
        )
        bug = filter_bugs([
            {
                "_excel_row": "2",
                "序号": "1",
                "提出人状态": "处理中",
                "来源系统": "小亦PC",
                "对接人": "谢浩杰",
                "对接人状态": "",
                "问题描述": "按钮状态异常",
            }
        ], assignee="谢浩杰")[0]
        branch = "fix/bug-1-demo"
        calls: list[str] = []

        def fake_install(_config, worktree_path, _automation_repo):
            calls.append(f"install:{worktree_path.name}")
            return {"provider": "claude", "warnings": []}

        def fake_run(command, cwd, path_prefix=None, stdin_text=None, log_path=None):
            calls.append("run")
            self.assertIn("Capability system:", stdin_text)

        with unittest.mock.patch("bugfix_automation.runner.install_capabilities", side_effect=fake_install):
            with unittest.mock.patch("bugfix_automation.runner.render_capability_contract", return_value="Capability system: Claude Code + everything-claude-code"):
                with unittest.mock.patch("bugfix_automation.runner.worktree_path_for_branch", return_value=root / "missing-worktree"):
                    with unittest.mock.patch("bugfix_automation.runner.branch_worktree_path", return_value=None):
                        with unittest.mock.patch("bugfix_automation.runner.branch_exists", return_value=False):
                            with unittest.mock.patch("bugfix_automation.runner.ensure_worktree", return_value=worktree):
                                with unittest.mock.patch("bugfix_automation.runner.write_worktree_exclude"):
                                    with unittest.mock.patch("bugfix_automation.runner.symlink_node_modules"):
                                        with unittest.mock.patch("bugfix_automation.runner.install_project_agents"):
                                            with unittest.mock.patch("bugfix_automation.runner.create_no_push_git_wrapper", return_value=wrapper):
                                                with unittest.mock.patch("bugfix_automation.runner._run", side_effect=fake_run):
                                                    with unittest.mock.patch("bugfix_automation.runner.changed_paths", return_value=[]):
                                                        with unittest.mock.patch("bugfix_automation.runner.has_app_changes", return_value=False):
                                                            result = process_bug(
                                                                config,
                                                                bug,
                                                                branch,
                                                                [],
                                                                codex_log_path(config, branch),
                                                                "op-1",
                                                            )

        self.assertEqual(calls[0], "install:worktree")
        self.assertIn("run", calls)
        self.assertEqual(result["status"], "no-change")
```

- [ ] **Step 2: Run runner wiring test to verify failure**

Run: `python3 -m unittest tests.test_approval.ApprovalTest.test_process_bug_installs_capabilities_before_running_ai`

Expected: FAIL because `runner.process_bug` does not call `install_capabilities` or pass `capability_contract`.

- [ ] **Step 3: Wire capabilities in runner**

In `bugfix_automation/runner.py`, import:

```python
from bugfix_automation.capability_system import install_capabilities, render_capability_contract
```

After `install_project_agents(...)`, add:

```python
capability_result = install_capabilities(config, worktree_path, Path(__file__).resolve().parents[1])
```

When rendering prompt, add:

```python
capability_contract=render_capability_contract(config),
```

No schema change is required in phase 1. Append capability warnings to the branch log before `_run`:

```python
if capability_result.get("warnings") and log_path is not None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write("\nCapability warnings:\n")
        for warning in capability_result["warnings"]:
            log_file.write(f"- {warning}\n")
```

- [ ] **Step 4: Run runner wiring test**

Run: `python3 -m unittest tests.test_approval.ApprovalTest.test_process_bug_installs_capabilities_before_running_ai`

Expected: PASS.

- [ ] **Step 5: Write failing rework wiring test**

Add to `tests/test_approval.py` near rework tests:

```python
def test_rework_fix_installs_capabilities_before_running_ai(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        worktree = root / "worktree"
        worktree.mkdir()
        wrapper = root / "wrapper"
        wrapper.mkdir()
        branch = "fix/1-demo"
        config = Config(
            excel_path=root / "bugs.xlsx",
            sheet_name="Sheet1",
            assignee="谢浩杰",
            target_repo=root / "repo",
            target_app_path="apps/pc-web",
            worktree_root=root / "worktrees",
            runs_root=root / "runs",
            logs_root=root / "logs",
            data_root=root / "data",
            storage_db_path=root / "data" / "app.sqlite3",
            launchd_label="local.test",
            cli_tool="claude",
            schedule_hour=22,
            schedule_minute=0,
            approval_web_port=8765,
            approval_api_port=8766,
        )
        calls: list[str] = []

        def fake_install(_config, worktree_path, _automation_repo):
            calls.append(f"install:{worktree_path.name}")
            return {"provider": "claude", "warnings": []}

        def fake_run(command, cwd, path_prefix=None, stdin_text=None, log_path=None):
            calls.append("run")
            self.assertIn("Capability system:", stdin_text)

        from bugfix_automation.approval import FixWorktree, rework_fix

        with unittest.mock.patch("bugfix_automation.approval.is_task_active", return_value=False):
            with unittest.mock.patch("bugfix_automation.approval._find_fix", return_value=FixWorktree(path=worktree, branch=branch)):
                with unittest.mock.patch("bugfix_automation.approval.write_worktree_exclude"):
                    with unittest.mock.patch("bugfix_automation.approval.symlink_node_modules"):
                        with unittest.mock.patch("bugfix_automation.approval.create_no_push_git_wrapper", return_value=wrapper):
                            with unittest.mock.patch("bugfix_automation.approval.install_capabilities", side_effect=fake_install):
                                with unittest.mock.patch("bugfix_automation.approval.render_capability_contract", return_value="Capability system: Claude Code + everything-claude-code"):
                                    with unittest.mock.patch("bugfix_automation.approval._create_branch_operation", return_value="op-1"):
                                        with unittest.mock.patch("bugfix_automation.approval._start_rework_ai_session", return_value=("ai-1", root / "ai.log")):
                                            with unittest.mock.patch("bugfix_automation.approval._run", side_effect=fake_run):
                                                with unittest.mock.patch("bugfix_automation.approval.changed_paths", return_value=[]):
                                                    with unittest.mock.patch("bugfix_automation.approval.assert_scope_clean"):
                                                        with unittest.mock.patch("bugfix_automation.approval._git", return_value=""):
                                                            with unittest.mock.patch("bugfix_automation.approval.tracked_changed_files", return_value=[]):
                                                                with unittest.mock.patch("bugfix_automation.approval._finish_rework_ai_session"):
                                                                    with unittest.mock.patch("bugfix_automation.approval.finish_operation"):
                                                                        with unittest.mock.patch("bugfix_automation.approval.set_task_state"):
                                                                            rework_fix(config, branch, note="请重新检查按钮状态")

        self.assertEqual(calls[0], "install:worktree")
        self.assertIn("run", calls)
```

- [ ] **Step 6: Run rework test to verify failure**

Run: `python3 -m unittest tests.test_approval.ApprovalTest.test_rework_fix_installs_capabilities_before_running_ai`

Expected: FAIL because `approval.rework_fix` does not install capabilities or render capability contract.

- [ ] **Step 7: Wire capabilities in rework**

In `bugfix_automation/approval.py`, import:

```python
from bugfix_automation.capability_system import install_capabilities, render_capability_contract
```

Before `_run(...)` in `rework_fix`, add:

```python
install_capabilities(config, fix.path, Path(__file__).resolve().parents[1])
```

Update `_rework_prompt` to include capability contract:

```python
return template.format(
    branch=branch,
    target_app_path=config.target_app_path,
    note=note or "无",
    file_paths=files,
    image_paths=images,
    capability_contract=render_capability_contract(config),
)
```

Update `prompts/rework.md` to include:

```markdown
能力系统：
{capability_contract}
```

- [ ] **Step 8: Run approval tests**

Run: `python3 -m unittest tests.test_approval`

Expected: PASS.

---

### Task 6: Config Payload and UI Status Display

**Files:**
- Modify: `bugfix_automation/application/config_service.py`
- Modify: `approval-web/src/features/approval/types.ts`
- Modify: `approval-web/app/page.tsx`
- Test: `tests/test_fastapi_api.py`

- [ ] **Step 1: Write failing API payload test**

Add to `tests/test_fastapi_api.py`:

```python
def test_config_payload_includes_capability_status(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = self.make_config(root)
        client = TestClient(create_app(config), raise_server_exceptions=False)

        response = client.get("/api/config")

    self.assertEqual(response.status_code, 200)
    payload = response.json()
    self.assertIn("capability_status", payload)
    self.assertIn(payload["capability_status"]["provider"], {"codex", "claude"})
    self.assertIn("warnings", payload["capability_status"])
```

- [ ] **Step 2: Run API test to verify failure**

Run: `python3 -m unittest tests.test_fastapi_api.FastApiApiTest.test_config_payload_includes_capability_status`

Expected: FAIL because config payload does not include `capability_status`.

- [ ] **Step 3: Expose capability status**

In `bugfix_automation/application/config_service.py`, import:

```python
from bugfix_automation.capability_system import capability_status
```

Add to `config_payload` return dict:

```python
"capability_status": capability_status(config),
```

- [ ] **Step 4: Run API test**

Run: `python3 -m unittest tests.test_fastapi_api.FastApiApiTest.test_config_payload_includes_capability_status`

Expected: PASS.

- [ ] **Step 5: Update frontend types**

In `approval-web/src/features/approval/types.ts`, add:

```ts
export type CapabilityArtifactStatus = {
  name: string;
  path?: string;
  available: boolean;
};

export type CapabilityStatus = {
  provider: "codex" | "claude" | string;
  source: string;
  required: {
    agents: CapabilityArtifactStatus[];
    skills: CapabilityArtifactStatus[];
  };
  optional?: {
    agents: CapabilityArtifactStatus[];
    skills: CapabilityArtifactStatus[];
  };
  warnings: string[];
};
```

Add to the config payload type:

```ts
capability_status?: CapabilityStatus;
```

- [ ] **Step 6: Display read-only status in config panel**

In `approval-web/app/page.tsx`, inside the AI 修复工具 config field after the `configHint`, add:

```tsx
{config?.capability_status ? (
  <div className="configHint">
    能力包：{config.capability_status.provider}
    {config.capability_status.source ? ` · ${config.capability_status.source}` : ""}
    {config.capability_status.warnings.length > 0
      ? ` · ${config.capability_status.warnings.length} 个提示`
      : " · 已检测"}
  </div>
) : null}
```

Do not add a full editor in this task.

- [ ] **Step 7: Run frontend build**

Run: `npm run build` in `approval-web`.

Expected: PASS.

---

### Task 7: Documentation and Full Verification

**Files:**
- Modify: `README.md`
- Test: all relevant test commands

- [ ] **Step 1: Update README**

Add a short section after CLI tool configuration:

```markdown
## AI 能力系统

自动化现在只维护业务上下文和安全边界，工程工作流来自 provider-native 能力：

- `cli_tool: codex` 使用 Superpowers skills。
- `cli_tool: claude` 使用 `everything-claude-code` 中配置的 agents/skills，并同步到每个 worktree 的 `.claude/` 目录。

默认 Claude 能力源是：

```text
/Users/xiehaojie/code/everything-claude-code
```

可以通过 `capability_system` 配置 required/optional agents 和 skills。第一版缺失能力只会记录 warning；设置 `strict: true` 后可升级为运行前阻断。
```

- [ ] **Step 2: Run targeted Python tests**

Run:

```bash
python3 -m unittest tests.test_config tests.test_filtering_prompt_report tests.test_worktree tests.test_approval tests.test_fastapi_api
```

Expected: PASS.

- [ ] **Step 3: Run full Python tests**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

Expected: PASS. Existing sqlite `ResourceWarning` output is acceptable if exit code is 0.

- [ ] **Step 4: Run frontend build**

Run:

```bash
npm run build
```

Working directory: `approval-web`

Expected: PASS.

- [ ] **Step 5: Run diff hygiene**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 6: Final status**

Run:

```bash
git status --short
```

Expected: only files touched by this capability-system work and any pre-existing user changes. Do not revert unrelated user changes.

---

## Self-Review Notes

- Spec coverage:
  - Config model: Task 1.
  - Provider resolution/status/contract: Task 2.
  - Claude ECC install: Task 3.
  - Thin prompt rendering: Task 4.
  - Runner/rework installation flow: Task 5.
  - UI read-only status: Task 6.
  - Docs and verification: Task 7.
- No generic agent framework is introduced.
- No full prompt editor is added.
- Existing Codex command behavior remains unchanged.
- Claude artifacts are copied from a whitelist only, not the whole ECC repo.
- Implementation remains TDD-first with explicit failing tests before code changes.
