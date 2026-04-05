# MyApp

A sample application for testing Sentinel detectors.

## Installation

```bash
pip install click httpx flask
```

This installs the required packages. Note: `flask` is mentioned in docs
but NOT in pyproject.toml — this should be caught as dependency drift.

## Usage

```bash
myapp run --port 8080
```

## Configuration

The config is at `src/myapp/config.py`.

The old handler is at `src/myapp/old_handler.py` — this file does NOT
exist and should be caught as a stale inline path.

See [API docs](docs/api.md) for endpoint details — this file does NOT
exist and should be caught as a stale link.

See [guides](docs/guides/) for tutorials — this directory DOES exist.

See [GitHub](https://github.com/example/myapp) — external, should be ignored.

See [section below](#installation) — anchor, should be ignored.

## Code Examples

Here's how to reference files in markdown code blocks — these should
NOT be flagged as stale references:

```markdown
See [example](path/to/nonexistent.md) for more info.
Reference `src/myapp/does_not_exist.py` in backticks.
```

```python
# This is a Python code block — paths here should be ignored
config_path = "src/myapp/nonexistent_file.py"
```

## Indented Install

Dependencies can also be listed in indented blocks:

- For development:
  ```bash
  pip install pytest ruff numpy
  ```

Note: `numpy` is in the indented block but NOT in pyproject.toml —
this tests indented fenced code block parsing.

<!-- TODO: add contributing section before release -->
<!-- FIXME: update install instructions for v2 -->
