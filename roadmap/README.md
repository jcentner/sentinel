# Roadmap

## Overview

Local Repo Sentinel development followed a phased approach through Phases 0–9, all of which are now complete. Future work uses a slice-based model tracked in [CURRENT-STATE.md](CURRENT-STATE.md).

## Completed Phases

| Phase | Title | Description |
|-------|-------|-------------|
| 0 | Project Foundation | Vision, architecture docs, ADRs, dev workflow |
| 1 | MVP Core | Core pipeline: 3 detectors, LLM judge, SQLite state, morning report, CLI |
| 2 | Docs-Drift Detector | First-class docs-drift detection (ADR-005) |
| 3 | Refinement | False-positive tuning, report UX, persistence scoring |
| 4 | Extended Detectors | Git-hotspots, complexity, eslint-runner, go-linter, rust-clippy |
| 5 | GitHub Integration | Issue creation from approved findings |
| 6 | Semantic Detectors | Cross-artifact LLM detectors: semantic docs-drift, test-code coherence |
| 6b | High-Value Deterministic | Unused deps, dead code, stale env detectors |
| 7 | Provider Abstraction | Pluggable model provider protocol (ADR-010) |
| 8 | Capability-Tiered Detectors | CapabilityTier infrastructure, enhanced modes |
| 9 | Configurability & Plugins | Detector selection, entry-points plugins, synthesis, setup flow |

Phase planning docs archived to `roadmap/archive/phases/`.
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
