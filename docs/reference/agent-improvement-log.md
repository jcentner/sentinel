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

### 2026-04-06 — Reviewer skipped again in Session 14 (repeat failure)
**Problem observed**: Session 14 implemented 4 slices (JSON CLI, eslint-runner, web clustering, eval metrics) touching 18+ files including new modules, schema migration, and new web routes — all committed without running the reviewer subagent. This is the same failure as Session 9 despite the explicit post-implementation checklist added after that incident. The reviewer (run in Session 15 at user prompting) found: 4 major doc-drift issues (schema version, routes table, detector table), 1 resource leak (unclosed connection), 1 performance issue (unbounded rglob), and 1 test coverage gap. All were trivially catchable.
**Affected file(s)**: No instruction file changes needed — the rules are already correct. This is a compliance failure, not a rule gap.
**Change made**: No instruction changes. Session 15 fixed all 6 reviewer findings. Documenting this entry as evidence that the review step must not be skipped even when implementing multiple slices in rapid succession.
**Expected benefit**: Reinforces that the reviewer subagent call is non-optional for any slice touching 3+ files, per the existing Step 5 checklist.
**Validation**: Next multi-slice session must show reviewer subagent invocation before each commit, not after human prompting.

### 2026-04-07 — Test quality never audited across 19 sessions
**Problem observed**: The autonomous builder accumulated 626 tests over 19 sessions and used "test count" and "coverage %" as the sole quality proxies. A systematic audit (Session 20) revealed: (1) the LLM judge path was never integration-tested — all 10 integration tests used `skip_judge=True`, meaning the most business-critical path (detector → context → prompt → judge → verdict → store) had no end-to-end coverage; (2) the `db_conn` fixture was copy-pasted identically into 7 test files while `conftest.py` was empty; (3) CI enforced line coverage but not branch coverage; (4) external tool detectors (ESLint, Clippy, Go linter, dep-audit) had zero real-tool integration tests — only the lint-runner had one. The agent never questioned whether 626 tests were testing the *right things*.
**Affected file(s)**: `.github/agents/autonomous-builder.agent.md`
**Change made**: No agent instruction changes needed — this is a periodic audit gap, not a rule gap. The fix was implementation: shared `conftest.py` fixture, 3 judge integration tests, `--cov-branch` in CI, and 4 real-tool conditional tests. Documenting as a learning: test quantity is not test quality. The autonomous loop's "Verify" step should periodically (every ~5 sessions) include a test suite audit: mock ratio, integration coverage of critical paths, fixture duplication, and branch coverage gaps.
**Expected benefit**: Future sessions will treat test quality as a periodic verification target, not just test count. Critical paths (LLM judge, external tool integration) will have regression guards.
**Validation**: The judge integration tests should catch any regression in the verdict storage path. The `--cov-branch` gate should surface uncovered branches in CI.
