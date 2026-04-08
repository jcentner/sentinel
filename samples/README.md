# Output Samples

> **Note**: These samples were generated early in development (Phase 1) and may not reflect the current output format. The system now has 14 detectors, finding synthesis, persistence tracking, and richer report formatting. Re-generate with `sentinel scan <repo> --skip-judge` for current output.

This directory contains excerpts of real Sentinel output from scanning its own repository.

- [sample-report.md](sample-report.md) — Morning report excerpt (markdown format)
- [sample-json-output.json](sample-json-output.json) — JSON output from `sentinel scan --json-output`
- [sample-cli-session.txt](sample-cli-session.txt) — Example CLI session

These samples were generated with `--skip-judge` (no LLM running). With an LLM judge via Ollama, findings would include relevance scoring and natural-language summaries.
