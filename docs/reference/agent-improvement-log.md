# Agent Improvement Log

Changes to Copilot instructions, prompts, agents, and workflow files. Each entry documents what was changed, why, and how the improvement will be validated.

## Format

```
### YYYY-MM-DD HH:MM — Brief title
**Problem observed**: What went wrong or was inefficient
**Affected file(s)**: Which instruction/prompt/agent files were changed
**Change made**: What was modified
**Expected benefit**: What should improve
**Validation**: How to confirm it worked
```

## Entries

### 2026-04-05 — Reviewer subagent skipped after significant implementation
**Problem observed**: Session 9 implemented a 4-file embedding system (ADR, schema migration, 3 new modules, 6 modified files). The autonomous loop (step 6) requires running the reviewer subagent after significant code changes, but this step was skipped entirely. The review only occurred because the human explicitly requested it. The review found 8 issues — 4 of which were trivially detectable (stale doc references in the same file that was edited, dead set entry, missing diagram update). These should have been caught before committing.
**Affected file(s)**: `.github/agents/autonomous-builder.agent.md`
**Change made**: Added a concrete post-implementation checklist to the "Verify" step in the autonomous loop. The checklist mandates: (1) grep for stale references when resolving OQs/TDs, (2) run the reviewer subagent for any slice touching 3+ files, (3) verify config values are threaded end-to-end when adding new config fields.
**Expected benefit**: Prevents the pattern of "tests pass → checkpoint → done" bypassing the review step. Catches docs-drift in the agent's own output — particularly ironic for a project whose value proposition is detecting docs-drift.
**Validation**: Next implementation session should include a reviewer subagent call before the commit. The review should find fewer medium-severity issues (target: 0 stale-reference findings).
