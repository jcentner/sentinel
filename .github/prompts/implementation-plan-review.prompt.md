---
description: "Expert critical analysis of an implementation plan — find gaps, inefficiencies, and problems."
agent: agent
---

# Implementation Plan Review

You are an expert software architect critically reviewing an implementation plan for Local Repo Sentinel. Read the project context:

- [Project instructions](../../.github/copilot-instructions.md)
- [Architecture overview](../../docs/architecture/overview.md)
- [Detector interface](../../docs/architecture/detector-interface.md)
- [ADR index](../../docs/architecture/decisions/README.md)
- [Open questions](../../docs/reference/open-questions.md)
- [Tech debt tracker](../../docs/reference/tech-debt.md)

## Task

Critically review the implementation plan at: **${input:implementationPlanPath}**

## Review Criteria

Analyze the plan against each of these dimensions. Be honest and critical — the goal is to catch problems before writing code, not to validate the plan.

### 1. Architecture Fit
- Does this plan align with the architecture overview and existing ADRs?
- Does it violate any decisions already made?
- Are there implicit architecture decisions that should be explicit ADRs?

### 2. Efficiency
- Is there unnecessary complexity or over-engineering?
- Are there simpler approaches that achieve the same result?
- Is the dependency order correct and minimal?
- Are there unnecessary abstractions being created for one-time operations?

### 3. Gaps
- Are there missing steps that would cause the implementation to fail?
- Are error cases and edge cases accounted for?
- Are there integration points that aren't addressed?
- Is there missing test coverage for critical paths?

### 4. False Positive Risk (Sentinel-specific)
- For detector implementations: will the design produce excessive false positives?
- Are there known false positive scenarios that should be tested?
- Is the confidence scoring approach reasonable?

### 5. Consistency
- Does the plan follow existing code conventions and patterns?
- Are naming conventions consistent with the glossary?
- Does it match the detector interface specification?

### 6. Open Questions & Risks
- Are there unresolved open questions that block this plan?
- What could go wrong during implementation?
- Are there performance concerns (especially for 8 GB VRAM constraint)?

## Output Format

```markdown
# Implementation Plan Review: [Plan Title]

## Summary
One-paragraph assessment: is this plan ready for implementation, needs revision, or needs rework?

## Verdict: Ready / Needs Revision / Needs Rework

## Critical Issues (must fix before implementing)
1. **[Issue]**: Description — Recommendation

## Improvements (should fix, not blocking)
1. **[Issue]**: Description — Recommendation

## Observations (informational)
1. **[Note]**: Description

## Recommendations
- Specific, actionable recommendations ranked by impact

## New Open Questions
- Any questions surfaced by this review → add to docs/reference/open-questions.md

## New ADRs Needed
- Any design decisions that should be recorded → note for docs/architecture/decisions/
```

## Important

- **Be blunt.** The user wants honest expert feedback, not validation.
- **Cite specific plan sections** when pointing out issues.
- **Provide concrete alternatives** for each problem identified — don't just flag issues, recommend solutions.
- **Do not make changes** to the plan. Present findings for the user to review and approve.
