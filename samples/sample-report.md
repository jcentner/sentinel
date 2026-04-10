# Sentinel Morning Report

**Repo**: /home/jacobcentner/sentinel/tests/fixtures/sample-repo
**Scan**: full | **Generated**: 2026-04-10 16:38 UTC
**Findings**: 32

## Summary

- **HIGH**: 5
- **MEDIUM**: 7
- **LOW**: 20

**New**: 32 | **Recurring**: 0

**By detector**: todo-scanner (8) · dead-code (7) · docs-drift (5) · stale-env (5) · unused-deps (3) · complexity (2) · lint-runner (2)

## HIGH

### code-quality

<details>
<summary><strong>3 related findings</strong> in <code>src/myapp</code></summary>

- **Complex function: process_records (cyclomatic complexity 21 (threshold: 10), 76 lines (threshold: 50))** — `src/myapp/processing.py`:6 (confidence: 95%) `[2ecef516b2abc111]`

  <details>
  <summary>Evidence (3 items)</summary>

  **code** from `src/myapp/processing.py`
  Lines 6–82
  ```
  Function process_records at src/myapp/processing.py:6
  ```

  **code** from `src/myapp/processing.py`
  Lines 1–11
  ```
     1 | """Data processing utilities — intentionally complex for benchmark testing."""
     2 | 
     3 | import os
     4 | 
     5 | 
     6 | def process_records(records, config):
     7 |     """Process a batch of records with validation and transformation.
     8 | 
     9 |     This function intentionally has high cyclomatic complexity (CC > 10)
    10 |     to exercise the complexity detector.
    11 |     """
  ```

  **git_history** from `src/myapp/processing.py`
  ```
  6a5d260 test(fixtures): expand sample-repo with complexity, stale-env, unused-deps coverage
  ```

  </details>

- **F401: `os` imported but unused** — `src/myapp/main.py`:3 (confidence: 100%) `[82b0d2b26752fe3b]`

  <details>
  <summary>Evidence (3 items)</summary>

  **lint_output** from `ruff:F401`
  Lines 3–3
  ```
  F401: `os` imported but unused
  Fix: Remove unused import: `os`
  ```

  **code** from `src/myapp/main.py`
  Lines 1–8
  ```
     1 | """Main application module."""
     2 | 
     3 | import os
     4 | 
     5 | # TODO: Add proper logging configuration
     6 | # This is a real TODO and should be caught.
     7 | 
     8 | 
  ```

  **git_history** from `src/myapp/main.py`
  ```
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

- **F841: Local variable `msg` is assigned to but never used** — `src/myapp/main.py`:19 (confidence: 100%) `[78ec7bcb471985c4]`

  <details>
  <summary>Evidence (3 items)</summary>

  **lint_output** from `ruff:F841`
  Lines 19–19
  ```
  F841: Local variable `msg` is assigned to but never used
  Fix: Remove assignment to unused variable `msg`
  ```

  **code** from `src/myapp/main.py`
  Lines 14–24
  ```
    14 |     data = {"key": "value"}  # HACK: hardcoded data for now
    15 | 
    16 |     template = "# TODO: this is inside a string, not a real TODO"  # noqa
    17 | 
    18 |     # A tricky case: string then real comment on one line
    19 |     msg = "# TODO: fake"  # TODO: this IS a real comment TODO
    20 | 
    21 |     # This should be caught — HACK but no description
    22 |     # XXX
    23 | 
    24 |     return data
  ```

  **git_history** from `src/myapp/main.py`
  ```
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

</details>

### todo-fixme

- **HACK: hardcoded data for now** — `src/myapp/main.py`:14 (confidence: 90%) `[4c7ef8fd1b27fbad]`

  <details>
  <summary>Evidence (4 items)</summary>

  **code** from `src/myapp/main.py`
  Lines 14–14
  ```
  data = {"key": "value"}  # HACK: hardcoded data for now
  ```

  **git_history** from `src/myapp/main.py`
  ```
  Added by Jacob Centner on 2026-04-04
  ```

  **code** from `src/myapp/main.py`
  Lines 9–19
  ```
     9 | def main():
    10 |     """Run the application."""
    11 |     # FIXME: Handle keyboard interrupt gracefully
    12 |     print("Starting myapp...")
    13 | 
    14 |     data = {"key": "value"}  # HACK: hardcoded data for now
    15 | 
    16 |     template = "# TODO: this is inside a string, not a real TODO"  # noqa
    17 | 
    18 |     # A tricky case: string then real comment on one line
    19 |     msg = "# TODO: fake"  # TODO: this IS a real comment TODO
  ```

  **git_history** from `src/myapp/main.py`
  ```
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

- **XXX: (no description)** — `src/myapp/main.py`:22 (confidence: 90%) `[03d7af4e3b72364a]`

  <details>
  <summary>Evidence (4 items)</summary>

  **code** from `src/myapp/main.py`
  Lines 22–22
  ```
  # XXX
  ```

  **git_history** from `src/myapp/main.py`
  ```
  Added by Jacob Centner on 2026-04-04
  ```

  **code** from `src/myapp/main.py`
  Lines 17–27
  ```
    17 | 
    18 |     # A tricky case: string then real comment on one line
    19 |     msg = "# TODO: fake"  # TODO: this IS a real comment TODO
    20 | 
    21 |     # This should be caught — HACK but no description
    22 |     # XXX
    23 | 
    24 |     return data
    25 | 
    26 | 
    27 | def helper():
  ```

  **git_history** from `src/myapp/main.py`
  ```
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

## MEDIUM

### config-drift

- **Undocumented env var: REDIS_URL** — `.env.example` (confidence: 75%) `[52110541922e6585]`

  <details>
  <summary>Evidence (2 items)</summary>

  **config** from `.env.example`
  ```
  Missing from docs: REDIS_URL
  ```

  **git_history** from `.env.example`
  ```
  6a5d260 test(fixtures): expand sample-repo with complexity, stale-env, unused-deps coverage
  ```

  </details>

### docs-drift

<details>
<summary><strong>3 related findings</strong> in <code>.</code></summary>

- **Stale link: [API docs](docs/api.md)** — `README.md`:27 (confidence: 95%) `[4a93a44418d0b900]`

  <details>
  <summary>Evidence (3 items)</summary>

  **doc** from `README.md`
  Lines 27–27
  ```
  See [API docs](docs/api.md) for endpoint details — this file does NOT
  ```

  **code** from `README.md`
  Lines 22–32
  ```
    22 | The config is at `src/myapp/config.py`.
    23 | 
    24 | The old handler is at `src/myapp/old_handler.py` — this file does NOT
    25 | exist and should be caught as a stale inline path.
    26 | 
    27 | See [API docs](docs/api.md) for endpoint details — this file does NOT
    28 | exist and should be caught as a stale link.
    29 | 
    30 | See [guides](docs/guides/) for tutorials — this directory DOES exist.
    31 | 
    32 | See [GitHub](https://github.com/example/myapp) — external, should be ignored.
  ```

  **git_history** from `README.md`
  ```
  fe24452 test(eval): add HTML comment TODO ground truth entries
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

- **Dependency drift: `flask` in docs but not in project** — `README.md` (confidence: 90%) `[d55c757b3ca6f56b]`

  <details>
  <summary>Evidence (2 items)</summary>

  **doc** from `README.md`
  ```
  Package `flask` found in install instructions
  ```

  **git_history** from `README.md`
  ```
  fe24452 test(eval): add HTML comment TODO ground truth entries
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

- **Dependency drift: `numpy` in docs but not in project** — `README.md` (confidence: 90%) `[a21cd6e5bd647978]`

  <details>
  <summary>Evidence (2 items)</summary>

  **doc** from `README.md`
  ```
  Package `numpy` found in install instructions
  ```

  **git_history** from `README.md`
  ```
  fe24452 test(eval): add HTML comment TODO ground truth entries
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

</details>

- **Stale link: [the overview](../overview.md)** — `docs/guides/getting-started.md`:3 (confidence: 95%) `[5fada7b8ce543d2e]`

  <details>
  <summary>Evidence (3 items)</summary>

  **doc** from `docs/guides/getting-started.md`
  Lines 3–3
  ```
  Refer to [the overview](../overview.md) for background — this file
  ```

  **code** from `docs/guides/getting-started.md`
  Lines 1–8
  ```
     1 | # Getting Started
     2 | 
     3 | Refer to [the overview](../overview.md) for background — this file
     4 | does NOT exist (stale link: should be caught).
     5 | 
     6 | See [README](../../README.md) — this DOES exist (should NOT be caught).
     7 | 
     8 | Config lives at `src/myapp/config.py` — this should resolve to repo root
  ```

  **git_history** from `docs/guides/getting-started.md`
  ```
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

### todo-fixme

- **FIXME: Handle keyboard interrupt gracefully** — `src/myapp/main.py`:11 (confidence: 90%) `[f6cc00f2f5fcefdc]`

  <details>
  <summary>Evidence (4 items)</summary>

  **code** from `src/myapp/main.py`
  Lines 11–11
  ```
  # FIXME: Handle keyboard interrupt gracefully
  ```

  **git_history** from `src/myapp/main.py`
  ```
  Added by Jacob Centner on 2026-04-04
  ```

  **code** from `src/myapp/main.py`
  Lines 6–16
  ```
     6 | # This is a real TODO and should be caught.
     7 | 
     8 | 
     9 | def main():
    10 |     """Run the application."""
    11 |     # FIXME: Handle keyboard interrupt gracefully
    12 |     print("Starting myapp...")
    13 | 
    14 |     data = {"key": "value"}  # HACK: hardcoded data for now
    15 | 
    16 |     template = "# TODO: this is inside a string, not a real TODO"  # noqa
  ```

  **git_history** from `src/myapp/main.py`
  ```
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

- **FIXME: update install instructions for v2** — `README.md`:64 (confidence: 90%) `[a03bd54f4c8c11f3]`

  <details>
  <summary>Evidence (4 items)</summary>

  **code** from `README.md`
  Lines 64–64
  ```
  <!-- FIXME: update install instructions for v2 -->
  ```

  **git_history** from `README.md`
  ```
  Added by Jacob Centner on 2026-04-05
  ```

  **code** from `README.md`
  Lines 59–64
  ```
    59 | 
    60 | Note: `numpy` is in the indented block but NOT in pyproject.toml —
    61 | this tests indented fenced code block parsing.
    62 | 
    63 | <!-- TODO: add contributing section before release -->
    64 | <!-- FIXME: update install instructions for v2 -->
  ```

  **git_history** from `README.md`
  ```
  fe24452 test(eval): add HTML comment TODO ground truth entries
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

## LOW

### code-quality

<details>
<summary><strong>8 related findings</strong> in <code>src/myapp</code></summary>

- **Complex function: long_report_generator (65 lines (threshold: 50))** — `src/myapp/processing.py`:85 (confidence: 95%) `[ef52c18a00bb35db]`

  <details>
  <summary>Evidence (3 items)</summary>

  **code** from `src/myapp/processing.py`
  Lines 85–150
  ```
  Function long_report_generator at src/myapp/processing.py:85
  ```

  **code** from `src/myapp/processing.py`
  Lines 80–90
  ```
    80 |         results.append(record)
    81 | 
    82 |     return {"results": results, "errors": errors, "total": len(records)}
    83 | 
    84 | 
    85 | def long_report_generator(data, options):
    86 |     """Generate a report with many sections.
    87 | 
    88 |     This function intentionally exceeds the 50-line body threshold
    89 |     to exercise the complexity detector's function-length check.
    90 |     """
  ```

  **git_history** from `src/myapp/processing.py`
  ```
  6a5d260 test(fixtures): expand sample-repo with complexity, stale-env, unused-deps coverage
  ```

  </details>

- **Unused function: process_records** — `src/myapp/processing.py`:6 (confidence: 70%) `[1a485ac92904a9ae]`

  <details>
  <summary>Evidence (3 items)</summary>

  **code** from `src/myapp/processing.py`
  Lines 6–6
  ```
  function process_records (line 6)
  ```

  **code** from `src/myapp/processing.py`
  Lines 1–11
  ```
     1 | """Data processing utilities — intentionally complex for benchmark testing."""
     2 | 
     3 | import os
     4 | 
     5 | 
     6 | def process_records(records, config):
     7 |     """Process a batch of records with validation and transformation.
     8 | 
     9 |     This function intentionally has high cyclomatic complexity (CC > 10)
    10 |     to exercise the complexity detector.
    11 |     """
  ```

  **git_history** from `src/myapp/processing.py`
  ```
  6a5d260 test(fixtures): expand sample-repo with complexity, stale-env, unused-deps coverage
  ```

  </details>

- **Unused function: long_report_generator** — `src/myapp/processing.py`:85 (confidence: 70%) `[48c97b8434860f16]`

  <details>
  <summary>Evidence (3 items)</summary>

  **code** from `src/myapp/processing.py`
  Lines 85–85
  ```
  function long_report_generator (line 85)
  ```

  **code** from `src/myapp/processing.py`
  Lines 80–90
  ```
    80 |         results.append(record)
    81 | 
    82 |     return {"results": results, "errors": errors, "total": len(records)}
    83 | 
    84 | 
    85 | def long_report_generator(data, options):
    86 |     """Generate a report with many sections.
    87 | 
    88 |     This function intentionally exceeds the 50-line body threshold
    89 |     to exercise the complexity detector's function-length check.
    90 |     """
  ```

  **git_history** from `src/myapp/processing.py`
  ```
  6a5d260 test(fixtures): expand sample-repo with complexity, stale-env, unused-deps coverage
  ```

  </details>

- **Unused constant: DATABASE_URL** — `src/myapp/config.py`:6 (confidence: 70%) `[01762f39e8f8218d]`

  <details>
  <summary>Evidence (3 items)</summary>

  **code** from `src/myapp/config.py`
  Lines 6–6
  ```
  constant DATABASE_URL (line 6)
  ```

  **code** from `src/myapp/config.py`
  Lines 1–11
  ```
     1 | """Application configuration."""
     2 | 
     3 | import os
     4 | 
     5 | # TODO: Load from environment variables instead of hardcoding
     6 | DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///myapp.db")
     7 | SECRET_KEY = "changeme"
     8 | DEBUG = True
     9 | 
    10 | # Undocumented env var (not in .env.example)
    11 | REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
  ```

  **git_history** from `src/myapp/config.py`
  ```
  6a5d260 test(fixtures): expand sample-repo with complexity, stale-env, unused-deps coverage
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

- **Unused constant: SECRET_KEY** — `src/myapp/config.py`:7 (confidence: 70%) `[3987e842ff41b1a1]`

  <details>
  <summary>Evidence (3 items)</summary>

  **code** from `src/myapp/config.py`
  Lines 7–7
  ```
  constant SECRET_KEY (line 7)
  ```

  **code** from `src/myapp/config.py`
  Lines 2–11
  ```
     2 | 
     3 | import os
     4 | 
     5 | # TODO: Load from environment variables instead of hardcoding
     6 | DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///myapp.db")
     7 | SECRET_KEY = "changeme"
     8 | DEBUG = True
     9 | 
    10 | # Undocumented env var (not in .env.example)
    11 | REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
  ```

  **git_history** from `src/myapp/config.py`
  ```
  6a5d260 test(fixtures): expand sample-repo with complexity, stale-env, unused-deps coverage
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

- **Unused constant: DEBUG** — `src/myapp/config.py`:8 (confidence: 70%) `[ee6580abf317e84b]`

  <details>
  <summary>Evidence (3 items)</summary>

  **code** from `src/myapp/config.py`
  Lines 8–8
  ```
  constant DEBUG (line 8)
  ```

  **code** from `src/myapp/config.py`
  Lines 3–11
  ```
     3 | import os
     4 | 
     5 | # TODO: Load from environment variables instead of hardcoding
     6 | DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///myapp.db")
     7 | SECRET_KEY = "changeme"
     8 | DEBUG = True
     9 | 
    10 | # Undocumented env var (not in .env.example)
    11 | REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
  ```

  **git_history** from `src/myapp/config.py`
  ```
  6a5d260 test(fixtures): expand sample-repo with complexity, stale-env, unused-deps coverage
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

- **Unused constant: REDIS_URL** — `src/myapp/config.py`:11 (confidence: 70%) `[38844cbae79190f6]`

  <details>
  <summary>Evidence (3 items)</summary>

  **code** from `src/myapp/config.py`
  Lines 11–11
  ```
  constant REDIS_URL (line 11)
  ```

  **code** from `src/myapp/config.py`
  Lines 6–11
  ```
     6 | DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///myapp.db")
     7 | SECRET_KEY = "changeme"
     8 | DEBUG = True
     9 | 
    10 | # Undocumented env var (not in .env.example)
    11 | REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
  ```

  **git_history** from `src/myapp/config.py`
  ```
  6a5d260 test(fixtures): expand sample-repo with complexity, stale-env, unused-deps coverage
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

- **Unused function: helper** — `src/myapp/main.py`:27 (confidence: 70%) `[81dfbdcf0ed1c4cd]`

  <details>
  <summary>Evidence (3 items)</summary>

  **code** from `src/myapp/main.py`
  Lines 27–27
  ```
  function helper (line 27)
  ```

  **code** from `src/myapp/main.py`
  Lines 22–32
  ```
    22 |     # XXX
    23 | 
    24 |     return data
    25 | 
    26 | 
    27 | def helper():
    28 |     """A simple helper."""
    29 |     # This mentions TODO mid-sentence — should NOT be caught
    30 |     # We should find TODOs in the codebase eventually.
    31 | 
    32 |     # This is far from comment — should not count as TODO
  ```

  **git_history** from `src/myapp/main.py`
  ```
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

</details>

### config-drift

<details>
<summary><strong>4 related findings</strong> in <code>.</code></summary>

- **Documented env var never used: ENABLE_CACHE** — `.env.example` (confidence: 80%) `[68302f0422f6a032]`

  <details>
  <summary>Evidence (2 items)</summary>

  **config** from `.env.example`
  ```
  Documented: ENABLE_CACHE
  ```

  **git_history** from `.env.example`
  ```
  6a5d260 test(fixtures): expand sample-repo with complexity, stale-env, unused-deps coverage
  ```

  </details>

- **Documented env var never used: LOG_LEVEL** — `.env.example` (confidence: 80%) `[a2760745ad467aab]`

  <details>
  <summary>Evidence (2 items)</summary>

  **config** from `.env.example`
  ```
  Documented: LOG_LEVEL
  ```

  **git_history** from `.env.example`
  ```
  6a5d260 test(fixtures): expand sample-repo with complexity, stale-env, unused-deps coverage
  ```

  </details>

- **Documented env var never used: MY_API_KEY** — `.env.example` (confidence: 80%) `[ebde6a9f62b4d742]`

  <details>
  <summary>Evidence (2 items)</summary>

  **config** from `.env.example`
  ```
  Documented: MY_API_KEY
  ```

  **git_history** from `.env.example`
  ```
  6a5d260 test(fixtures): expand sample-repo with complexity, stale-env, unused-deps coverage
  ```

  </details>

- **Documented env var never used: WEBHOOK_SECRET** — `.env.example` (confidence: 80%) `[66d055faac8103e0]`

  <details>
  <summary>Evidence (2 items)</summary>

  **config** from `.env.example`
  ```
  Documented: WEBHOOK_SECRET
  ```

  **git_history** from `.env.example`
  ```
  6a5d260 test(fixtures): expand sample-repo with complexity, stale-env, unused-deps coverage
  ```

  </details>

</details>

### dependency

<details>
<summary><strong>3 related findings</strong> in <code>.</code></summary>

- **Unused dependency: click** — `pyproject.toml` (confidence: 80%) `[d4d79ca3d51e2459]`

  <details>
  <summary>Evidence (2 items)</summary>

  **config** from `pyproject.toml`
  ```
  Declared: click
  Expected imports: click
  ```

  **git_history** from `pyproject.toml`
  ```
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

- **Unused dependency: httpx** — `pyproject.toml` (confidence: 80%) `[2f90ef3c534a7e8c]`

  <details>
  <summary>Evidence (2 items)</summary>

  **config** from `pyproject.toml`
  ```
  Declared: httpx
  Expected imports: httpx
  ```

  **git_history** from `pyproject.toml`
  ```
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

- **Unused dependency: sqlalchemy** — `pyproject.toml` (confidence: 80%) `[f26cdcc820a01e19]`

  <details>
  <summary>Evidence (2 items)</summary>

  **config** from `pyproject.toml`
  ```
  Declared: sqlalchemy
  Expected imports: sqlalchemy
  ```

  **git_history** from `pyproject.toml`
  ```
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

</details>

### docs-drift

- **Stale path reference: `src/myapp/old_handler.py`** — `README.md`:24 (confidence: 80%) `[bf68d6286934b035]`

  <details>
  <summary>Evidence (3 items)</summary>

  **doc** from `README.md`
  Lines 24–24
  ```
  The old handler is at `src/myapp/old_handler.py` — this file does NOT
  ```

  **code** from `README.md`
  Lines 19–29
  ```
    19 | 
    20 | ## Configuration
    21 | 
    22 | The config is at `src/myapp/config.py`.
    23 | 
    24 | The old handler is at `src/myapp/old_handler.py` — this file does NOT
    25 | exist and should be caught as a stale inline path.
    26 | 
    27 | See [API docs](docs/api.md) for endpoint details — this file does NOT
    28 | exist and should be caught as a stale link.
    29 | 
  ```

  **git_history** from `README.md`
  ```
  fe24452 test(eval): add HTML comment TODO ground truth entries
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

### todo-fixme

<details>
<summary><strong>3 related findings</strong> in <code>src/myapp</code></summary>

- **TODO: Load from environment variables instead of hardcoding** — `src/myapp/config.py`:5 (confidence: 90%) `[416083921daac531]`

  <details>
  <summary>Evidence (4 items)</summary>

  **code** from `src/myapp/config.py`
  Lines 5–5
  ```
  # TODO: Load from environment variables instead of hardcoding
  ```

  **git_history** from `src/myapp/config.py`
  ```
  Added by Jacob Centner on 2026-04-04
  ```

  **code** from `src/myapp/config.py`
  Lines 1–10
  ```
     1 | """Application configuration."""
     2 | 
     3 | import os
     4 | 
     5 | # TODO: Load from environment variables instead of hardcoding
     6 | DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///myapp.db")
     7 | SECRET_KEY = "changeme"
     8 | DEBUG = True
     9 | 
    10 | # Undocumented env var (not in .env.example)
  ```

  **git_history** from `src/myapp/config.py`
  ```
  6a5d260 test(fixtures): expand sample-repo with complexity, stale-env, unused-deps coverage
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

- **TODO: Add proper logging configuration** — `src/myapp/main.py`:5 (confidence: 90%) `[b6df26f43e94e390]`

  <details>
  <summary>Evidence (4 items)</summary>

  **code** from `src/myapp/main.py`
  Lines 5–5
  ```
  # TODO: Add proper logging configuration
  ```

  **git_history** from `src/myapp/main.py`
  ```
  Added by Jacob Centner on 2026-04-04
  ```

  **code** from `src/myapp/main.py`
  Lines 1–10
  ```
     1 | """Main application module."""
     2 | 
     3 | import os
     4 | 
     5 | # TODO: Add proper logging configuration
     6 | # This is a real TODO and should be caught.
     7 | 
     8 | 
     9 | def main():
    10 |     """Run the application."""
  ```

  **git_history** from `src/myapp/main.py`
  ```
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

- **TODO: this IS a real comment** — `src/myapp/main.py`:19 (confidence: 90%) `[5def427a3c866458]`

  <details>
  <summary>Evidence (4 items)</summary>

  **code** from `src/myapp/main.py`
  Lines 19–19
  ```
  msg = "# TODO: fake"  # TODO: this IS a real comment TODO
  ```

  **git_history** from `src/myapp/main.py`
  ```
  Added by Jacob Centner on 2026-04-04
  ```

  **code** from `src/myapp/main.py`
  Lines 14–24
  ```
    14 |     data = {"key": "value"}  # HACK: hardcoded data for now
    15 | 
    16 |     template = "# TODO: this is inside a string, not a real TODO"  # noqa
    17 | 
    18 |     # A tricky case: string then real comment on one line
    19 |     msg = "# TODO: fake"  # TODO: this IS a real comment TODO
    20 | 
    21 |     # This should be caught — HACK but no description
    22 |     # XXX
    23 | 
    24 |     return data
  ```

  **git_history** from `src/myapp/main.py`
  ```
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

</details>

- **TODO: add contributing section before release** — `README.md`:63 (confidence: 90%) `[d535f320c5677b9a]`

  <details>
  <summary>Evidence (4 items)</summary>

  **code** from `README.md`
  Lines 63–63
  ```
  <!-- TODO: add contributing section before release -->
  ```

  **git_history** from `README.md`
  ```
  Added by Jacob Centner on 2026-04-05
  ```

  **code** from `README.md`
  Lines 58–64
  ```
    58 |   ```
    59 | 
    60 | Note: `numpy` is in the indented block but NOT in pyproject.toml —
    61 | this tests indented fenced code block parsing.
    62 | 
    63 | <!-- TODO: add contributing section before release -->
    64 | <!-- FIXME: update install instructions for v2 -->
  ```

  **git_history** from `README.md`
  ```
  fe24452 test(eval): add HTML comment TODO ground truth entries
  fa5f658 fix(detectors): 7 precision/recall fixes + eval test with ground truth
  ```

  </details>

## Actions

```bash
sentinel suppress <ID> -r "reason"  # Suppress a false positive
sentinel approve <ID>               # Approve for GitHub issue creation
sentinel create-issues --dry-run     # Create GitHub issues from approved findings
sentinel history                     # View past runs
```

---
*Report generated by Sentinel v0.1.0*
