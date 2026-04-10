# Output Samples

> **Updated**: Session 27 (2026-04-10). Generated from `tests/fixtures/sample-repo` with `--skip-judge` (no LLM running). With an LLM judge, findings include relevance scoring and natural-language summaries.

This directory contains excerpts of real Sentinel output from scanning the sample-repo test fixture (32 findings across 7 detectors).

- [sample-report.md](sample-report.md) — Morning report (markdown format)
- [sample-json-output.json](sample-json-output.json) — JSON output from `sentinel scan --json-output`
- [sample-cli-session.txt](sample-cli-session.txt) — Example CLI session (scan, show, history, doctor)

To regenerate: `sentinel scan tests/fixtures/sample-repo --skip-judge -o samples/sample-report.md`
