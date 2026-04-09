# Test Fixture: sample-repo Ground Truth

This file documents the expected findings in the sample-repo fixture.
Used by the eval test to measure precision@k and recall.

## Expected TRUE POSITIVES (scanner SHOULD find these)

### docs-drift: stale references
1. **README.md** link to `docs/api.md` — file does not exist
2. **README.md** inline path `src/myapp/old_handler.py` — file does not exist
3. **docs/guides/getting-started.md** link to `../overview.md` — file does not exist

### docs-drift: dependency drift
4. **README.md** mentions `pip install flask` but flask is not in pyproject.toml
5. **README.md** indented install block mentions `pip install numpy` but numpy is not in pyproject.toml

### todo-fixme
6. **src/myapp/main.py:5** — `# TODO: Add proper logging configuration`
7. **src/myapp/main.py:11** — `# FIXME: Handle keyboard interrupt gracefully`
8. **src/myapp/main.py:14** — `# HACK: hardcoded data for now`
9. **src/myapp/main.py:20** — `# TODO: this IS a real comment TODO` (second TODO on line)
10. **src/myapp/main.py:23** — `# XXX` (no description)
11. **src/myapp/config.py:3** — `# TODO: Load from environment variables`

### todo-fixme: HTML comment TODOs in markdown
12. **README.md** — `<!-- TODO: add contributing section before release -->`
13. **README.md** — `<!-- FIXME: update install instructions for v2 -->`

### dead-code: unused symbols
14. **src/myapp/config.py:4** — Unused constant: `DATABASE_URL` (never imported elsewhere)
15. **src/myapp/config.py:5** — Unused constant: `SECRET_KEY` (never imported elsewhere)
16. **src/myapp/config.py:6** — Unused constant: `DEBUG` (never imported elsewhere)
17. **src/myapp/main.py:27** — Unused function: `helper` (never imported elsewhere)
18. **src/myapp/processing.py** — Unused function: `process_records` (never imported)
19. **src/myapp/processing.py** — Unused function: `long_report_generator` (never imported)
20. **src/myapp/config.py** — Unused constant: `REDIS_URL` (never imported elsewhere)

### complexity: high cyclomatic complexity and long functions
21. **src/myapp/processing.py** — `process_records` CC=21, 76 lines (HIGH)
22. **src/myapp/processing.py** — `long_report_generator` 65 lines (LOW)

### stale-env: documented vars not used in code
23. **`.env.example`** — `ENABLE_CACHE` documented but never referenced in source
24. **`.env.example`** — `LOG_LEVEL` documented but never referenced in source
25. **`.env.example`** — `MY_API_KEY` documented but never referenced in source
26. **`.env.example`** — `WEBHOOK_SECRET` documented but never referenced in source

### stale-env: undocumented env var
27. **`.env.example`** — `REDIS_URL` used in code but not documented in `.env.example`

### unused-deps: declared dependencies not imported in source
28. **pyproject.toml** — `click` declared but never imported
29. **pyproject.toml** — `httpx` declared but never imported
30. **pyproject.toml** — `sqlalchemy` declared but never imported

## Expected TRUE NEGATIVES (scanner should NOT find these)

### docs-drift: valid references
- README.md link to `docs/guides/` — directory exists
- README.md link to `https://github.com/example/myapp` — external URL
- README.md link to `#installation` — anchor
- getting-started.md link to `../../README.md` — file exists
- getting-started.md inline path `src/myapp/config.py` — file exists at repo root

### docs-drift: code block content (NOT real references)
- README.md: `[example](path/to/nonexistent.md)` inside ```markdown block
- README.md: `src/myapp/does_not_exist.py` inside ```python block
- README.md: `src/myapp/nonexistent_file.py` inside ```python block

### docs-drift: matching deps
- README.md: `click`, `httpx` — both in pyproject.toml

### todo-fixme: false patterns
- src/myapp/main.py:16 — `"# TODO: this is inside a string"` (string literal)
- src/myapp/main.py:19 — `"# TODO: fake"` (string literal part)
- src/myapp/main.py:27 — `# We should find TODOs` (mid-sentence, proximity > 5)

## Stretch goals (known limitations, may not detect)

### Detectors excluded from eval (by design)
- **dep-audit**: Requires real `pip-audit` execution against installed packages
- **git-hotspots**: Requires git history with multiple commits (fixture is flat directory)
