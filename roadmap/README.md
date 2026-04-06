# Roadmap

## Overview

Local Repo Sentinel development follows a phased approach. Each phase has a planning doc, implementation plan, review, and completion checklist — see the [Prompt Guide](../.github/prompts/PROMPT-GUIDE.md) for the development workflow.

## Phases

| Phase | Title | Status | Description |
|-------|-------|--------|-------------|
| 0 | Project Foundation | **Complete** | Vision, architecture docs, ADRs, dev workflow, prompt system |
| 1 | MVP Core | **Complete** | Core pipeline: 3 detectors, LLM judge, SQLite state, morning report, CLI |
| 2 | Docs-Drift Detector | **Complete** | First-class docs-drift detection (ADR-005) |
| 3 | Refinement | **Complete** | False-positive tuning, report UX, persistence scoring |
| 4 | Extended Detectors | **Complete** | Git-hotspots, complexity, eslint-runner, go-linter, rust-clippy |
| 5 | GitHub Integration | **Complete** | Issue creation from approved findings |

## Phase details

Phase planning docs live in `roadmap/phases/` and are created via the `/phase-plan` prompt.

### Phase 0: Project Foundation
- Project vision and strategy docs
- Architecture overview and detector interface design
- ADR system with 6 initial decisions
- Development workflow (prompts, agents, instructions)
- Open questions, tech debt, and glossary systems
- Competitive analysis and critical review

### Phase 1: MVP Core
- ~~Resolve OQ-001 (implementation language)~~ → ADR-007
- ~~Resolve OQ-007 (eval criteria)~~ → ADR-008
- Core run loop: trigger → detect → gather context → judge → report
- 2-3 initial detectors: `lint-runner`, `todo-scanner`, `dep-audit`
- SQLite state store with finding fingerprinting
- LLM judge via Ollama
- Morning report (markdown)
- CLI to run and review

### Phase 2: Docs-Drift Detector
- Docs-drift extraction (README, JSDoc, config docs)
- LLM comparison for semantic drift
- Stale reference detection (deterministic)
- Confidence scoring per drift pattern

### Phase 3: Refinement
- ~~False-positive suppression UX~~ ✅
- ~~Finding persistence scoring (recurring = higher confidence)~~ ✅
- ~~Report format improvements~~ ✅
- ~~Incremental run optimization~~ ✅

### Phase 4: Extended Detectors
- ~~Git-hotspot analysis~~ ✅
- SQL anti-pattern detection (SQLFluff + LLM) — deferred
- Semgrep integration — deferred
- Complexity/dead-code heuristics — deferred

### Phase 5: GitHub Integration
- ~~GitHub API issue creation~~ ✅
- ~~Approval workflow~~ ✅
- ~~Issue dedup against existing GitHub issues~~ ✅
- Rate limiting and error handling — future enhancement

## Future (unscheduled)
- Multi-repo support
- ~~Web UI for report review and approval~~ ✅ (Session 11–13: full triage UI with bulk actions)
- Watch mode (continuous development)
- Custom detector plugin system
- Team mode / shared findings
