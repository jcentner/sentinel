# Sentinel Prompt Files — Usage Guide

Reusable prompt files for the Sentinel development workflow via GitHub Copilot Chat in VS Code.

## Quick Start

1. Open Copilot Chat (Ctrl+Shift+I or the Chat sidebar)
2. Type `/` to see available prompts
3. Select a prompt (e.g., `/phase-plan Phase 1 MVP`)
4. Optionally add context after the prompt name
5. Review output → approve changes → agent applies them

## Development Cycle

These prompts codify the Sentinel development workflow. Run them in order for each phase:

```
┌──────────────────────────────────────────────────────────────────────┐
│                      Sentinel Dev Cycle                              │
│                                                                      │
│  /phase-plan ──→ /implementation-plan ──→ /implementation-plan-review│
│       │                  │                         │                 │
│   (resolve open     (create file-by-file     (expert critical       │
│    questions)        checklist)                analysis of plan)     │
│                                                    │                 │
│                                              /implement              │
│                                                    │                 │
│                                              (write code,           │
│                                               ask when ambiguous)    │
│                                                    │                 │
│  /phase-complete ←── /security-audit ←──── /code-review             │
│       │                                                              │
│   (update docs,                                                      │
│    record lessons,                                                   │
│    record ADRs)                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

| Step | Prompt | What It Does |
|------|--------|--------------|
| 1 | `/phase-plan` | Create a phase planning doc with features, dependencies, acceptance criteria, open questions |
| 2 | `/implementation-plan` | Create a file-by-file implementation checklist from a phase doc |
| 3 | `/implementation-plan-review` | Expert critical analysis of the implementation plan — find gaps, inefficiencies, problems |
| 4 | `/implement` | Execute the plan section-by-section — write code, run tests, ask when ambiguous |
| 5 | `/code-review` | Review code against Sentinel conventions, patterns, and quality standards |
| 6 | `/security-audit` | Security audit across the codebase |
| 7 | `/phase-complete` | Update docs, record lessons learned, record ADRs, mark phase complete |

## All Prompts

### Development Cycle

| Prompt | What It Does | When to Run |
|--------|--------------|-------------|
| `/phase-plan` | Create a phase planning doc with features, dependencies, criteria, open questions | Starting a new phase |
| `/implementation-plan` | Create a file-by-file implementation checklist from a phase doc | After phase plan open questions resolved |
| `/implementation-plan-review` | Critically analyze the implementation plan for gaps, inefficiencies, problems | After implementation plan is drafted |
| `/implement` | Execute the implementation plan — write code, ask questions, run tests | After implementation plan review approved |
| `/code-review` | Review code against Sentinel conventions, quality standards | After implementing a feature or phase |
| `/security-audit` | Security audit: dependency check, input validation, secrets, API surface | After major changes or periodically |
| `/phase-complete` | Update docs, record ADRs, record lessons, mark phase complete | After code review + security audit pass |

### Strategy & Vision

| Prompt | What It Does | When to Run |
|--------|--------------|-------------|
| `/vision-update` | Review and update the vision lock to reflect shipped reality and forward direction | After completing a phase, shipping significant features, or shifting project direction |
| `/phase-complete` | Update docs, record ADRs, record lessons, mark phase complete | After code review + security audit pass |

## How These Work

- **Prompt files** (`.prompt.md`) are invoked manually via `/` commands in Chat. They're task-specific.
- **Instruction files** (`.instructions.md` in `.github/instructions/`) are applied automatically when Copilot works on matching files.
- **Custom agents** (`.agent.md` in `.github/agents/`) define specialized roles with tool restrictions and handoffs.
- The prompt's `agent: agent` frontmatter runs it in agent mode with full tool access.
- **Markdown links** in the prompt body attach referenced files as context automatically.
- Prompts link to `copilot-instructions.md` for project context rather than repeating it.

## Design Principles

Based on [VS Code prompt file best practices](https://code.visualstudio.com/docs/copilot/customization/prompt-files):

1. **No restrictive `tools` list** — The agent inherits all default tools. Only add `tools` to restrict.
2. **Markdown links for context** — Referenced files are attached automatically.
3. **Discovery-first** — Prompts discover relevant code dynamically rather than hardcoding paths.
4. **Input variables** — Use `${input:variable}` for run-time parameters.
5. **Descriptions in frontmatter** — Each prompt has a `description` for autocomplete.
6. **No duplicated instructions** — Prompts link to `copilot-instructions.md` for shared context.
7. **Doc verification before fixes** — Prompts cite authoritative docs before proposing changes.

## Custom Agents

| Agent | What It Does | Tools |
|-------|-------------|-------|
| `planner` | Research and planning — read-only analysis, no code changes | Read-only tools only |
| `reviewer` | Code review with Sentinel conventions | Read-only + terminal (for tests) |

Agents support **handoffs** — after planning, a button appears to hand off to implementation.

## Troubleshooting

- **Prompt doesn't appear in `/` menu?** — Check file is in `.github/prompts/` with `.prompt.md` extension.
- **Agent can't find files?** — Don't add a `tools` field unless restricting. Default agent has full access.
- **Prompt not picking up context?** — Verify Markdown links use correct relative paths from the prompt file's location.
- **Diagnostics** — Right-click in Chat view → Diagnostics to see all loaded prompts and errors.
