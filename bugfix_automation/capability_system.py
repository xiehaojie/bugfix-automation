from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

from bugfix_automation.ai_cli import ai_cli_kind
from bugfix_automation.config import CapabilityProviderConfig, Config


def resolve_capability_provider(config: Config) -> str:
    provider = config.capability_system.provider.strip().lower()
    if provider in {"claude", "codex"}:
        return provider
    return "claude" if ai_cli_kind(config.cli_tool) == "claude" else "codex"


def active_provider_config(config: Config) -> CapabilityProviderConfig:
    if resolve_capability_provider(config) == "claude":
        return config.capability_system.claude
    return config.capability_system.codex


def capability_status(config: Config) -> dict[str, Any]:
    provider = resolve_capability_provider(config)
    provider_config = active_provider_config(config)
    if provider == "claude":
        return _claude_status(provider_config)
    return _codex_status(provider_config)


def install_capabilities(config: Config, worktree: Path, automation_repo: Path) -> dict[str, Any]:
    _ = automation_repo
    provider = resolve_capability_provider(config)
    if provider == "codex":
        return capability_status(config)

    provider_config = config.capability_system.claude
    source = Path(provider_config.source).expanduser()
    copied_agents: list[str] = []
    copied_skills: list[str] = []
    warnings: list[str] = []

    _copy_claude_agents(
        source,
        worktree,
        provider_config.required_agents,
        required=True,
        copied_agents=copied_agents,
        warnings=warnings,
    )
    _copy_claude_agents(
        source,
        worktree,
        provider_config.optional_agents,
        required=False,
        copied_agents=copied_agents,
        warnings=warnings,
    )
    _copy_claude_skills(
        source,
        worktree,
        provider_config.required_skills,
        required=True,
        copied_skills=copied_skills,
        warnings=warnings,
    )
    _copy_claude_skills(
        source,
        worktree,
        provider_config.optional_skills,
        required=False,
        copied_skills=copied_skills,
        warnings=warnings,
    )

    return {
        "provider": "claude",
        "source": str(source),
        "copied_agents": copied_agents,
        "copied_skills": copied_skills,
        "warnings": warnings,
    }


def render_capability_contract(config: Config) -> str:
    provider = resolve_capability_provider(config)
    provider_config = active_provider_config(config)
    status = capability_status(config)
    warnings = "\n".join(f"- {warning}" for warning in status["warnings"]) or "- None detected"
    if provider == "claude":
        agents = _configured_names(provider_config.required_agents, provider_config.optional_agents)
        skills = _configured_names(provider_config.required_skills, provider_config.optional_skills)
        return (
            "Capability system: Claude Code + everything-claude-code\n\n"
            "Use provider-native Claude Code capabilities from everything-claude-code when available.\n"
            f"Configured agents: {agents}\n"
            f"Configured skills: {skills}\n\n"
            "Do not replace installed agents or skills with a local prompt imitation.\n"
            "If a required capability is unavailable, state that clearly in the final report.\n\n"
            f"Capability warnings:\n{warnings}"
        )

    skills = _configured_names(provider_config.required_skills, provider_config.optional_skills)
    return (
        "Capability system: Codex + Superpowers\n\n"
        "Use provider-native Codex capabilities from Superpowers when applicable.\n"
        f"Configured skills: {skills}\n\n"
        "Do not replace installed skills with a local prompt imitation.\n"
        "If a required capability is unavailable, state that clearly in the final report.\n\n"
        f"Capability warnings:\n{warnings}"
    )


def _claude_status(provider_config: CapabilityProviderConfig) -> dict[str, Any]:
    source = Path(provider_config.source).expanduser()
    required_agents = [
        _artifact_status(name, source / "agents" / f"{name}.md")
        for name in provider_config.required_agents
    ]
    optional_agents = [
        _artifact_status(name, source / "agents" / f"{name}.md")
        for name in provider_config.optional_agents
    ]
    required_skills = [
        _artifact_status(name, source / "skills" / name)
        for name in provider_config.required_skills
    ]
    optional_skills = [
        _artifact_status(name, source / "skills" / name)
        for name in provider_config.optional_skills
    ]
    warnings = [
        f"Missing required Claude agent: {item['name']}"
        for item in required_agents
        if not item["available"]
    ]
    warnings.extend(
        f"Missing required Claude skill: {item['name']}"
        for item in required_skills
        if not item["available"]
    )
    return {
        "provider": "claude",
        "source": str(source),
        "required": {"agents": required_agents, "skills": required_skills},
        "optional": {"agents": optional_agents, "skills": optional_skills},
        "warnings": warnings,
    }


def _codex_status(provider_config: CapabilityProviderConfig) -> dict[str, Any]:
    required_skills = [
        _superpowers_skill_status(name)
        for name in provider_config.required_skills
    ]
    optional_skills = [
        _superpowers_skill_status(name)
        for name in provider_config.optional_skills
    ]
    warnings = [
        f"Missing required Superpowers skill: {item['name']}"
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


def _copy_claude_agents(
    source: Path,
    worktree: Path,
    agents: tuple[str, ...],
    *,
    required: bool,
    copied_agents: list[str],
    warnings: list[str],
) -> None:
    target = worktree / ".claude" / "agents"
    for name in agents:
        requirement = "required" if required else "optional"
        if not _valid_artifact_name(name):
            warnings.append(f"Invalid {requirement} Claude agent name: {name}")
            continue
        source_file = source / "agents" / f"{name}.md"
        if not source_file.is_file():
            warnings.append(f"Missing {requirement} Claude agent: {name}")
            continue
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target / source_file.name)
        copied_agents.append(name)


def _copy_claude_skills(
    source: Path,
    worktree: Path,
    skills: tuple[str, ...],
    *,
    required: bool,
    copied_skills: list[str],
    warnings: list[str],
) -> None:
    target = worktree / ".claude" / "skills"
    for name in skills:
        requirement = "required" if required else "optional"
        if not _valid_artifact_name(name):
            warnings.append(f"Invalid {requirement} Claude skill name: {name}")
            continue
        source_dir = source / "skills" / name
        if not source_dir.is_dir():
            warnings.append(f"Missing {requirement} Claude skill: {name}")
            continue
        target_dir = target / name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source_dir, target_dir)
        copied_skills.append(name)


def _valid_artifact_name(name: str) -> bool:
    path = Path(name)
    return bool(name) and not path.is_absolute() and path.name == name and name not in {".", ".."}


def _artifact_status(name: str, path: Path) -> dict[str, Any]:
    return {"name": name, "path": str(path), "available": path.exists()}


def _superpowers_skill_status(skill_name: str) -> dict[str, Any]:
    path = _superpowers_skill_path(skill_name)
    return {
        "name": skill_name,
        "path": str(path) if path is not None else "",
        "available": path is not None,
    }


def _superpowers_skill_path(skill_name: str) -> Path | None:
    local_name = skill_name.split(":", 1)[-1]
    for root in _superpowers_roots():
        if not root.exists():
            continue
        for path in root.glob(f"**/skills/{local_name}/SKILL.md"):
            return path
    return None


def _superpowers_roots() -> tuple[Path, Path]:
    cache = Path.home() / ".codex" / "plugins" / "cache"
    return (
        cache / "claude-plugins-official" / "superpowers",
        cache / "openai-curated" / "superpowers",
    )


def _configured_names(required: tuple[str, ...], optional: tuple[str, ...]) -> str:
    names = (*required, *optional)
    return ", ".join(names) if names else "none configured"
