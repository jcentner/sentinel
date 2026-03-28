---
description: "Security audit across the Sentinel codebase."
agent: agent
---

# Security Audit

You are performing a security audit of Local Repo Sentinel. Read the project context:

- [Project instructions](../../.github/copilot-instructions.md)
- [Architecture overview](../../docs/architecture/overview.md)

## Task

Perform a security audit of the Sentinel codebase. Focus area (optional): **${input:focusArea:full codebase}**

## Audit Areas

### 1. Dependency Security
- Run dependency audit tools (npm audit, pip-audit, or equivalent)
- Check for known vulnerabilities in direct and transitive dependencies
- Flag outdated dependencies with known CVEs

### 2. Subprocess Execution
- Sentinel runs external tools (linters, git, test runners). Check for:
  - Command injection in subprocess calls
  - Unsanitized user input in commands
  - Proper shell escaping

### 3. File System Access
- Sentinel reads repo files. Check for:
  - Path traversal vulnerabilities
  - Symlink following outside repo boundary
  - Proper handling of untrusted file content

### 4. Ollama API Interaction
- Check for:
  - Prompt injection from untrusted repo content fed to the model
  - Proper error handling for model responses
  - No secrets leaked in prompts

### 5. GitHub API (Issue Creation)
- Check for:
  - Token scoping (minimal permissions)
  - No token leakage in logs or reports
  - Proper authentication handling
  - Rate limiting awareness

### 6. SQLite State Store
- Check for:
  - SQL injection (should be using parameterized queries)
  - Proper file permissions on the database
  - No sensitive data stored unencrypted

### 7. Report Output
- Morning reports may contain code snippets. Check for:
  - No accidental inclusion of secrets from scanned code
  - Proper sanitization if reports are rendered as HTML

## Doc Verification

Before proposing fixes, verify against authoritative documentation:
- OWASP guidelines for relevant vulnerability classes
- Tool-specific security docs (Ollama API, GitHub API, SQLite)

Each finding must cite the doc or standard that informed the recommendation.

## Output Format

| Severity | Area | Finding | Evidence | Recommendation | Doc Reference |
|----------|------|---------|----------|----------------|---------------|
| Critical/High/Medium/Low | area | description | what you found | how to fix | source |

## Important

- **Do not make changes until the user approves.**
- Prioritize findings by actual exploitability, not theoretical risk.
- Sentinel runs locally — the threat model is different from a web service.
