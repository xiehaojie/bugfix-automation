# Capability System Design

Date: 2026-05-21

## Goal

Rebuild the automation prompt system around real upstream capabilities instead of maintaining local prompts that imitate those capabilities.

The automation should keep ownership of bug-specific business context, safety boundaries, worktree setup, logging, and approval flow. Engineering workflow guidance should come from the real provider-native capability systems:

- Codex uses Superpowers skills.
- Claude Code uses artifacts from `everything-claude-code`.

This keeps prompts smaller, makes behavior easier to configure, and avoids a weak local copy of Superpowers or ECC.

## Non-Goals

- Do not build a new generic agent framework.
- Do not fork or rewrite Superpowers or `everything-claude-code`.
- Do not make every prompt template editable in the UI in the first version.
- Do not require both Codex and Claude to behave identically.
- Do not remove current Codex compatibility aliases in the first migration.

## Current Problems

The current system has three kinds of coupling:

- Prompt templates contain weak local descriptions of planning, fixing, verification, and summarization.
- `.codex/agents/*.toml` are small and project-specific, so the Claude conversion path produces shallow agents.
- Provider behavior is split across runner, prompt rendering, worktree agent installation, summary generation, and API helpers.

The result works, but it is brittle. Adding Claude by converting Codex agents creates agents that look right structurally but do not carry the depth of `everything-claude-code`.

## Design Summary

Introduce a thin capability adapter layer:

```text
bugfix_automation/capability_system.py
```

The adapter resolves the active provider, loads capability configuration, validates availability, installs provider-native artifacts into the worktree, and renders a small capability contract for the main bug prompt.

The main bug prompt becomes mostly business context:

- Excel row and normalized bug fields
- Raw Excel row
- workspace/repo/target path
- scope and allowed edit boundaries
- screenshots and extra context files
- final output contract

The engineering workflow comes from the selected capability pack.

## Configuration

Runtime configuration should support a `capability_system` section. Values may come from `config.yaml`, SQLite settings, or environment overrides using the existing configuration precedence.

Example:

```yaml
capability_system:
  provider: auto

  codex:
    source: superpowers
    required_skills:
      - superpowers:using-superpowers
      - superpowers:test-driven-development
      - superpowers:systematic-debugging
      - superpowers:verification-before-completion
      - superpowers:requesting-code-review
    optional_skills:
      - superpowers:subagent-driven-development

  claude:
    source: /Users/xiehaojie/code/everything-claude-code
    required_agents:
      - planner
      - architect
      - tdd-guide
      - code-reviewer
      - typescript-reviewer
      - build-error-resolver
    optional_agents:
      - security-reviewer
      - performance-optimizer
    required_skills:
      - tdd-workflow
      - coding-standards
      - verification-loop
```

`provider: auto` means infer the provider from `cli_tool`:

- tool name containing `claude` resolves to Claude.
- tool name containing `codex` resolves to Codex.
- unknown tools default to Codex-compatible behavior for backwards compatibility.

## Data Model

Add immutable config dataclasses:

```python
from dataclasses import dataclass, field


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
        default_factory=lambda: CapabilityProviderConfig(source="superpowers")
    )
    claude: CapabilityProviderConfig = field(default_factory=CapabilityProviderConfig)
```

Add `capability_system: CapabilitySystemConfig` to `Config`.

## Capability Adapter API

`bugfix_automation/capability_system.py` should expose a narrow API:

```python
def resolve_capability_provider(config: Config) -> str:
    ...

def capability_status(config: Config) -> dict[str, Any]:
    ...

def install_capabilities(config: Config, worktree_path: Path, automation_repo: Path) -> dict[str, Any]:
    ...

def render_capability_contract(config: Config) -> str:
    ...
```

### `resolve_capability_provider`

Returns `codex` or `claude` based on explicit config first, then `cli_tool`.

### `capability_status`

Returns a structured status object:

```json
{
  "provider": "claude",
  "source": "/Users/xiehaojie/code/everything-claude-code",
  "required": {
    "agents": [{"name": "planner", "available": true}],
    "skills": [{"name": "tdd-workflow", "available": true}]
  },
  "warnings": []
}
```

This status is used in logs and later can be exposed in the approval UI.

### `install_capabilities`

For Claude:

- Copy selected ECC agents from `<source>/agents/<name>.md` to `<worktree>/.claude/agents/<name>.md`.
- Copy selected ECC skills from `<source>/skills/<name>/` to `<worktree>/.claude/skills/<name>/`.
- Missing required artifacts are reported as warnings in phase 1, not hard failures.
- Optional artifacts are skipped if missing.

For Codex:

- Do not copy ECC artifacts.
- Keep the existing `.codex/agents` installation for backwards compatibility.
- Add capability availability warnings for missing Superpowers skill paths when detectable.

### `render_capability_contract`

Returns a provider-specific contract inserted near the top of the main bug prompt.

Codex example:

```text
Capability system: Codex + Superpowers

Use the installed Superpowers skills when applicable:
- superpowers:using-superpowers
- superpowers:test-driven-development
- superpowers:systematic-debugging
- superpowers:verification-before-completion
- superpowers:requesting-code-review

Do not replace those workflows with a local approximation. If a required skill is unavailable, state that clearly in the final report.
```

Claude example:

```text
Capability system: Claude Code + everything-claude-code

Use the project-local ECC agents and skills installed under .claude/.
Relevant agents include planner, architect, tdd-guide, code-reviewer, typescript-reviewer, and build-error-resolver.
Relevant skills include tdd-workflow, coding-standards, and verification-loop.

Do not imitate those workflows manually when an installed agent or skill is available. If a required artifact is unavailable, state that clearly in the final report.
```

## Prompt Rendering

Keep `render_codex_prompt` as a backwards-compatible public function name, but make it call the capability system internally.

The final prompt structure should be:

```text
1. Provider identity and capability contract
2. Mission for this bug
3. Hard safety constraints
4. Workspace context
5. Excel selected fields
6. Raw Excel row
7. Screenshots and context paths
8. Verification contract
9. Output contract
```

The prompt should no longer define local versions of TDD, planning, code review, or verification workflows. It may name the required stage outcomes, but not duplicate upstream methodology.

## Worktree Installation Flow

`process_bug` should install capabilities after creating the worktree and before rendering/running the prompt:

```text
ensure_worktree
write_worktree_exclude
symlink_node_modules
install_project_agents for legacy Codex agents
install_capabilities for provider-native artifacts
render prompt with capability contract
run AI CLI
```

For rework flows, capabilities should also be installed before calling the CLI so that Claude can use ECC agents/skills during follow-up changes.

## Provider Behavior

### Codex

Codex continues to use the existing command generation:

```text
codex exec --full-auto --cd <worktree> --image <path> -
```

The capability contract instructs Codex to use Superpowers skills. Availability detection is best-effort because the runtime skill environment may differ from local filesystem paths.

### Claude

Claude continues to use:

```text
claude --print --permission-mode bypassPermissions
```

When screenshots are present, the automation grants Claude access to screenshot parent directories via `--add-dir`. The prompt also includes the image paths.

Claude capability installation is file-based and deterministic because ECC agents and skills live in the local `everything-claude-code` repo.

## Fallback Strategy

Phase 1 uses soft validation:

- Missing required Codex Superpowers skills produce warnings.
- Missing required Claude ECC agents or skills produce warnings.
- The run continues, and the final prompt instructs the model to report missing capabilities.

Phase 2 can introduce hard validation:

- If `capability_system.strict: true`, missing required artifacts block the run before the AI CLI starts.

This avoids surprising failures during the first migration.

## Approval UI

The first version does not need a full editor. It should expose read-only capability status in config payload so the frontend can show:

```text
AI tool: Claude Code
Capability source: everything-claude-code
Agents: planner, architect, tdd-guide, code-reviewer...
Skills: tdd-workflow, coding-standards, verification-loop...
Warnings: missing security-reviewer
```

Editing capability config in the UI can be added later.

## Testing Strategy

Add focused tests before implementation:

- Config parses `capability_system` from YAML and SQLite settings.
- Provider resolution chooses Claude for `cli_tool=claude` and Codex for `cli_tool=codex`.
- Claude capability installation copies only configured ECC agents and skills.
- Missing required Claude artifacts appear in `capability_status` warnings.
- Codex contract includes required Superpowers skills.
- Claude contract includes configured ECC agents and skills.
- Prompt rendering includes the capability contract and does not contain old weak agent instructions.
- Rework flow installs capabilities before invoking the CLI.

Existing tests for command generation, image handling, worktree safety, config updates, and prompt rendering should remain green.

## Migration Plan

1. Add config dataclasses and parsing for `capability_system`.
2. Add `capability_system.py` with provider resolution, status, install, and contract rendering.
3. Extend worktree exclude and changed-file filters to ignore `.claude/skills`.
4. Wire capability installation into initial bug runs and rework runs.
5. Rewrite prompt templates to use `{capability_contract}` and remove local workflow imitation.
6. Expose capability status through config payload.
7. Update README with provider capability behavior.

## Risks and Mitigations

### Risk: Superpowers availability is hard to detect from inside a spawned Codex run

Mitigation: Start with best-effort filesystem checks and explicit prompt-level reporting. Add strict checks later only after runtime paths are stable.

### Risk: Copying too many ECC artifacts into every worktree creates noise

Mitigation: Use an explicit whitelist from config. Do not copy the entire ECC repo.

### Risk: Claude may not automatically invoke installed agents or skills from non-interactive `--print`

Mitigation: The capability contract explicitly names the relevant agents and skills. If needed later, add provider-specific command flags or project settings after verifying Claude Code behavior.

### Risk: Existing Codex prompt tests depend on old wording

Mitigation: Update tests around behavior, not exact wording. Preserve hard constraints: target scope, no push, no automatic commit, verification required.

## Success Criteria

- Running with `cli_tool=codex` produces a prompt that references Superpowers skills and keeps existing Codex command behavior.
- Running with `cli_tool=claude` installs configured ECC agents and skills into the worktree before invoking Claude.
- The main fix prompt becomes thinner and no longer duplicates local versions of TDD/review/verification workflows.
- Capability status is structured and visible to logs or config payload.
- Existing tests pass, and new tests cover provider resolution, artifact installation, contract rendering, and missing-artifact warnings.
