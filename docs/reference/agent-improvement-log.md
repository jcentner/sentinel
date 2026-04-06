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

### 2026-04-06 — Docs update skipped after major UI implementation
**Problem observed**: Session 12 shipped a complete web UI redesign (12 files changed, 3 new pages, 3 new routes, dark mode, GitHub issues workflow). The autonomous loop Step 7 ("Document and continue") explicitly requires updating: vision revisions, architecture overview, README, open questions, tech debt, and glossary. None of these were updated in the implementation commit. The user had to ask "What about docs, vision, etc updates for this UI direction?" to trigger the doc reconciliation. This is the same class of failure as the Session 9 reviewer skip — implementation pressure causes the agent to jump from "tests pass" to "checkpoint" without running the doc sync step.
**Affected file(s)**: `.github/agents/autonomous-builder.agent.md`
**Change made**: Added explicit doc-sync checklist to Step 7 of the autonomous loop. The checklist requires: for any slice that adds new user-facing features, before committing, check whether each doc in the standard list (vision, architecture, README, OQ, TD, glossary) references the changed capability and is still accurate.
**Expected benefit**: Prevents "ship code, update checkpoint, skip doc alignment" pattern. Ensures vision revisions are created when the shipped scope exceeds the last vision revision's spec.
**Validation**: Next feature implementation session should produce doc updates in the same commit as the implementation, not as a follow-up after human prompting.
