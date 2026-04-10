# Test Repositories

Curated open-source repos for validating Sentinel's detectors on real-world codebases. Selected to exercise different detector strengths — cross-artifact drift, multi-language support, complex dependency trees, and rapidly-evolving projects where docs tend to lag.

## Quick start

```bash
# Clone a few repos and scan them
mkdir -p ~/sentinel-test-repos && cd ~/sentinel-test-repos

git clone --depth=1 https://github.com/fastapi/fastapi
sentinel scan fastapi

git clone --depth=1 https://github.com/astral-sh/ruff
sentinel scan ruff

git clone --depth=1 https://github.com/jazzband/pip-tools
sentinel scan pip-tools
```

## Recommended repos

### Python — docs-drift and complexity detectors

| Repo | Why it's useful | Key detectors exercised |
|------|----------------|------------------------|
| [fastapi/fastapi](https://github.com/fastapi/fastapi) | Excellent docs, fast-moving. Docs sometimes lag behind new features. | semantic-drift, docs-drift, complexity |
| [jazzband/pip-tools](https://github.com/jazzband/pip-tools) | Moderate size, clear test suite, dependency tooling (meta). | test-coherence, unused-deps, lint-runner |
| [pallets/flask](https://github.com/pallets/flask) | Mature, well-documented, has accumulated some legacy drift. | docs-drift, dead-code, complexity |
| [encode/httpx](https://github.com/encode/httpx) | Modern async HTTP client, solid test coverage. | test-coherence, dead-code, lint-runner |
| [pydantic/pydantic](https://github.com/pydantic/pydantic) | Complex codebase, Rust core + Python bindings, active development. | complexity, docs-drift, semantic-drift |

### JavaScript / TypeScript — ESLint and cross-artifact detectors

| Repo | Why it's useful | Key detectors exercised |
|------|----------------|------------------------|
| [vercel/next.js](https://github.com/vercel/next.js) | Massive monorepo, many packages, heavy docs. Warning: very large. | docs-drift, unused-deps, eslint-runner |
| [shadcn-ui/ui](https://github.com/shadcn-ui/ui) | Popular component library, evolving fast, good test case for stale docs. | docs-drift, eslint-runner, dead-code |
| [TanStack/query](https://github.com/TanStack/query) | Multi-framework, docs-heavy, frequent releases. | semantic-drift, docs-drift, unused-deps |

### Go — Go linter detector

| Repo | Why it's useful | Key detectors exercised |
|------|----------------|------------------------|
| [charmbracelet/bubbletea](https://github.com/charmbracelet/bubbletea) | Clean Go project, fun TUI framework. | go-linter, docs-drift, todo-scanner |
| [junegunn/fzf](https://github.com/junegunn/fzf) | Popular CLI tool, Go + shell, practical test case. | go-linter, docs-drift, complexity |

### Rust — Clippy detector

| Repo | Why it's useful | Key detectors exercised |
|------|----------------|------------------------|
| [BurntSushi/ripgrep](https://github.com/BurntSushi/ripgrep) | Well-maintained CLI tool, rich docs, multiple crates. | rust-clippy, docs-drift, complexity |

### Multi-language / mixed

| Repo | Why it's useful | Key detectors exercised |
|------|----------------|------------------------|
| [supabase/supabase](https://github.com/supabase/supabase) | TS + Go + docs site. Rapid growth = high drift potential. Warning: large. | docs-drift, semantic-drift, eslint-runner, unused-deps |
| [localstack/localstack](https://github.com/localstack/localstack) | Python, heavy AWS service emulation, complex configs. | stale-env, docs-drift, complexity, dep-audit |

## Tips

- Use `--depth=1` when cloning to save disk space — Sentinel doesn't need full git history for most detectors (except `git-hotspots`, which needs ~100 commits).
- For large repos (next.js, supabase), use `--target` to scan specific subdirectories first.
- Run `sentinel scan <repo> --skip-judge` first to see raw findings before using LLM resources.
- Compare results across model providers/sizes using `sentinel benchmark <repo>`.

## Validation workflow

For systematic validation, scan a few repos and check:

1. **Precision**: Are the findings real issues? Manually verify 20-30 findings.
2. **False positive patterns**: What types of FPs appear? File them as detector improvements.
3. **Cross-artifact value**: Do semantic-drift and test-coherence find things the deterministic detectors miss?

```bash
# Full validation workflow
sentinel scan fastapi --db validation.db
sentinel scan pip-tools --db validation.db
sentinel serve . --db validation.db
# Review findings in the web UI, approve/suppress, note patterns
```
