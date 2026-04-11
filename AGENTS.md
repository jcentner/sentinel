# Local Repo Sentinel

A local, evidence-backed repository issue triage system for overnight code health monitoring.

## Conventions

- **Language**: Python
- **Checkpoint file**: `roadmap/CURRENT-STATE.md` — read this first every session
- **Vision lock**: `docs/vision/VISION-LOCK.md` — highest-authority document, versioned in place with changelog
- **ADRs**: Record significant decisions in `docs/architecture/decisions/`
- **Open questions**: Track uncertainty in `docs/reference/open-questions.md`
- **Tech debt**: Track compromises in `docs/reference/tech-debt.md`
- **Stack skills**: `.github/skills/` — technology-specific skills that ground agents in official docs

## Development Workflow

This project uses an autonomous build loop. The agent reads the checkpoint, identifies the next slice of work, implements it, reviews it, commits it, and checkpoints.

**Slice protocol** — for every unit of work:
1. Implement the change
2. Run tests — do not proceed if tests fail
3. Review code (invoke reviewer subagent or self-review for 1-2 file changes)
4. Fix Critical/Major findings
5. Commit with `type(scope): description` format (feat, fix, docs, refactor, test, chore)
6. Update `roadmap/CURRENT-STATE.md`

## Rules

- **Vision lock update rules**: Minor updates (within-scope) may be made in place with a minor version bump and changelog entry. Scope/goal changes require human approval — propose them in `roadmap/CURRENT-STATE.md` first.
- Run tests before committing — never commit broken tests
- Update docs when code changes affect documented behavior
- Record new design decisions as ADRs
- Record compromises in the tech debt tracker
- New terms go in `docs/reference/glossary.md`
- When adopting a new technology, create a stack skill in `.github/skills/` before writing implementation code

## Authority Order (highest first)

1. Vision lock (`docs/vision/VISION-LOCK.md`)
2. ADRs (`docs/architecture/decisions/`)
3. Architecture docs
4. Roadmap and planning docs
5. Open questions
6. Instructions and prompts

Lower-priority artifacts must be updated to match higher-priority ones.

## Document Health Rules

Growing documents erode their usefulness. Enforce these targets:

| Document | Target | Rule |
|----------|--------|------|
| `VISION-LOCK.md` | <200 lines | Strategic content only. Keep 2 most recent changelog entries inline; archive older ones to git history. "What Exists Today" is product-level summary, not per-detector/per-command lists. |
| `tech-debt.md` | Active items at top | Resolved items in a `## Resolved` section at the bottom. When resolved exceeds 30 items, archive to `tech-debt-resolved.md`. |
| `README.md` | <150 lines | Problem statement, quick start, link to wiki. Delegate CLI reference, web UI docs, config, scheduling, architecture to wiki or docs/. |
| `CURRENT-STATE.md` | Current session only | Replace previous session's summary on each new session start. Historical data lives in git history. |

Before committing a doc change, check if any key doc has grown past its target. If so, prune in the same commit.
