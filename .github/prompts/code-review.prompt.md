---
description: "Review code against Sentinel conventions, quality standards, and architecture decisions."
agent: agent
---

# Code Review

You are reviewing code for Local Repo Sentinel. Read the project context:

- [Project instructions](../../.github/copilot-instructions.md)
- [Architecture overview](../../docs/architecture/overview.md)
- [Detector interface](../../docs/architecture/detector-interface.md)
- [ADR index](../../docs/architecture/decisions/README.md)
- [Open questions](../../docs/reference/open-questions.md)
- [Glossary](../../docs/reference/glossary.md)

## Task

Review recent changes. If a specific scope is provided, focus there: **${input:reviewScope:recent changes}**

## Review Dimensions

### 1. Architecture Compliance
- Do changes align with existing ADRs?
- Is the detector interface followed correctly?
- Is the model interaction going through the `ModelProvider` protocol as specified (ADR-010)?
- Is state managed via SQLite (ADR-004)?

### 2. Code Quality
- Is the code simple and readable?
- Are there unnecessary abstractions or over-engineering?
- Are error cases handled at system boundaries?
- Is naming consistent with the glossary?

### 3. Test Quality
- Are there tests for new functionality?
- Do detector tests cover both true positives AND known false positives?
- Are tests meaningful (not just boilerplate)?

### 4. Docs Consistency
- If code changes affect documented behavior, are docs updated?
- Do any changes introduce docs-drift?
- Are new terms added to the glossary?

### 5. False Positive Risk (for detector code)
- Could this detector produce excessive false positives?
- Is confidence scoring reasonable?
- Are edge cases handled?

### 6. Security
- Input validation at system boundaries?
- No hardcoded secrets?
- GitHub API calls properly scoped and authenticated?
- No command injection in subprocess calls?

## Output Format

Present findings as a table:

| Severity | File | Finding | Recommendation |
|----------|------|---------|----------------|
| Critical / Major / Minor / Nit | path | description | fix |

Then a summary: overall assessment, any blocking issues, and whether the changes are ready to merge.

## Important

- **Do not make changes** until the user approves.
- Be specific — cite file paths and line numbers.
- Distinguish between blocking issues and style preferences.
