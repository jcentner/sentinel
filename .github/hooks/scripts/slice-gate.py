#!/usr/bin/env python3
"""Stop hook for the autonomous builder agent.

Prevents premature stopping by checking:
1. Whether stop_hook_active is set (prevents infinite loops)
2. Whether the phase is marked complete/blocked in CURRENT-STATE.md
3. Whether CI lint gates pass (ruff + mypy)

If any check fails, blocks the stop and tells the agent what to fix.
"""
import json
import os
import subprocess
import sys


def _block(reason: str) -> None:
    """Emit a blocking Stop response and exit."""
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "decision": "block",
                "reason": reason,
            }
        },
        sys.stdout,
    )


def _run_ci_checks(cwd: str) -> str | None:
    """Run ruff and mypy. Returns failure message or None if all pass."""
    checks = [
        ([sys.executable, "-m", "ruff", "check", "src/", "tests/"], "ruff"),
        ([sys.executable, "-m", "mypy", "src/sentinel/", "--strict"], "mypy"),
    ]
    failures: list[str] = []
    for cmd, name in checks:
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, cwd=cwd, timeout=90,
            )
        except FileNotFoundError:
            # Tool not installed — skip rather than block
            continue
        except subprocess.TimeoutExpired:
            failures.append(f"{name}: timed out after 90s")
            continue
        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip()
            # Truncate to avoid exceeding hook output limits
            if len(output) > 2000:
                output = output[:2000] + "\n... (truncated)"
            failures.append(f"{name} failed:\n{output}")

    if failures:
        return (
            "CI lint checks failed. Fix these before concluding:\n\n"
            + "\n\n".join(failures)
        )
    return None


def main():
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        input_data = {}

    # Prevent infinite loop — if we already blocked once, let it stop
    if input_data.get("stop_hook_active", False):
        json.dump({}, sys.stdout)
        return

    cwd = input_data.get("cwd", ".")

    # --- Gate 1: Phase status ---
    checkpoint = os.path.join(cwd, "roadmap", "CURRENT-STATE.md")

    phase_complete = False
    if os.path.exists(checkpoint):
        with open(checkpoint, encoding="utf-8") as f:
            content = f.read()

        for line in content.splitlines():
            stripped = line.strip().lower()
            if "**phase status**:" in stripped:
                if "complete" in stripped or "blocked" in stripped:
                    phase_complete = True
                break  # Only check the first occurrence

    if not phase_complete:
        _block(
            "Phase is not yet complete. Check roadmap/CURRENT-STATE.md "
            "for remaining work. Before stopping, ensure you have: "
            "(1) run tests on your changes, "
            "(2) invoked the reviewer subagent on changed files, "
            "(3) fixed any Critical/Major findings, "
            "(4) committed your work, "
            "(5) updated CURRENT-STATE.md. "
            "If the phase IS complete, set **Phase Status** to "
            "'Complete' in CURRENT-STATE.md. "
            "If you are blocked and need human input, set it to "
            "'Blocked: [reason]'."
        )
        return

    # --- Gate 2: CI lint checks ---
    ci_failure = _run_ci_checks(cwd)
    if ci_failure:
        _block(ci_failure)
        return

    # All gates passed — allow stop
    json.dump({}, sys.stdout)


if __name__ == "__main__":
    main()
