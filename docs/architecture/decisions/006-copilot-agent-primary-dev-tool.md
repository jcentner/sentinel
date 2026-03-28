# ADR-006: GitHub Copilot agent mode as primary development tool

**Status**: Accepted
**Date**: 2026-03-28
**Deciders**: Project founder

## Context

This project needs a primary development methodology. The founder works extensively with AI-assisted tooling and wants the development process itself to be well-structured, repeatable, and documented.

## Decision

Local Repo Sentinel is primarily developed using GitHub Copilot in VS Code agent mode with Claude Opus 4.6. The development workflow is codified as:

1. **Reusable prompt files** (`.github/prompts/`) — slash commands for each dev cycle step
2. **Always-on instructions** (`.github/copilot-instructions.md`) — project context auto-included
3. **File-based instructions** (`.github/instructions/`) — language/framework-specific conventions
4. **Custom agents** (`.github/agents/`) — specialized roles (planner, reviewer)

The dev cycle follows a phased approach:
```
/phase-plan → /implementation-plan → /implementation-plan-review → /implement → /code-review → /security-audit → /phase-complete
```

Key design principles for the prompts:
- No restrictive `tools` lists (agent inherits all defaults)
- Markdown links for context attachment
- Discovery-first patterns (dynamic, not hardcoded paths)
- Doc verification before fixes (cite authoritative docs)
- Handoffs between agents for guided workflows

## Consequences

**Positive**:
- Development process is documented and repeatable
- Prompts capture institutional knowledge about the project
- New contributors can follow the same workflow
- The prompt system itself is a publishable/demonstrable artifact

**Negative**:
- Dependent on Copilot agent mode and VS Code
- Prompt quality needs ongoing maintenance
- Claude Opus 4.6 model availability is Copilot-dependent

## Alternatives considered

- **Claude Code CLI**: Viable but diverges from the founder's primary workflow in VS Code.
- **Cursor / other AI IDEs**: Lock-in to a specific editor. VS Code + Copilot is mainstream and portable.
- **No structured prompts**: Ad-hoc prompting works but loses repeatability and institutional knowledge capture.
