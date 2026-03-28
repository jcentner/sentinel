---
description: "Execute an implementation plan — write code, run tests, ask when ambiguous."
agent: agent
---

# Implement

You are implementing code for Local Repo Sentinel following an approved implementation plan. Read the project context:

- [Project instructions](../../.github/copilot-instructions.md)
- [Architecture overview](../../docs/architecture/overview.md)
- [Detector interface](../../docs/architecture/detector-interface.md)

## Task

Execute the implementation plan at: **${input:implementationPlanPath}**

## Rules

1. **Follow the plan.** Implement in the order specified. Do not skip steps or reorder without asking.
2. **Ask when ambiguous.** If a step is unclear or you see multiple valid approaches, ask before proceeding. Do not guess.
3. **Run tests after each component.** Don't wait until the end — verify each piece works.
4. **Check the checklist.** Mark items as complete in the implementation plan as you go.
5. **Flag deviations.** If you need to deviate from the plan (e.g., the plan assumed a library API that doesn't exist), explain why and get approval.
6. **Update docs if needed.** If your implementation changes something documented, update the docs in the same commit. Check for docs-drift.
7. **Record tech debt.** If you take a shortcut, add it to `docs/reference/tech-debt.md`.
8. **Record new ADRs.** If a significant design decision is made during implementation, note it for recording as an ADR.

## Process

For each section of the implementation plan:

1. Read the section requirements
2. Search the codebase for relevant existing code and patterns
3. Implement the code
4. Write/update tests
5. Run the tests
6. Fix any failures
7. Move to the next section

## Quality Standards

- Prefer simple, well-tested code over clever abstractions
- Every detector finding must cite concrete evidence
- False positive prevention matters more than feature coverage
- Test both true positive and known false positive scenarios
- No lint errors in new code

## Do not

- Create files not specified in the implementation plan without asking
- Add features beyond what the plan specifies
- Skip tests to move faster
- Make architecture decisions without checking existing ADRs
