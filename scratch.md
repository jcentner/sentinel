Human-only scratchpad, do not modify


## Next
Use docs/analysis/project-history.md to write post or posts about this 

Run on other repos I have like wyoclear and use insights to refine further 

Example of how semantic docs-drift detector works. Accuracy, precision, recall? 


Notes on potential expansions (hold off for now) 

Tier 2: Strategic extensions (new territory)
4. New high-value detectors: intent-drift and arch-drift.
These were mentioned as potential "Phase 10" but never designed. The concept: detect when implementation intent has drifted from stated purpose (e.g., a function that grew far beyond its docstring's description) or when architectural patterns have drifted (e.g., a service that was supposed to be stateless now has state). These are the hardest problems and would require at minimum standard tier models. They're also the most differentiated — nobody else attempts this.

5. CI/CD config drift detector.
Another mentioned-but-undesigned detector: does your CI pipeline still match your actual build process? Do your GitHub Actions test the languages you actually use? This is a cross-artifact inconsistency that fits Sentinel's model perfectly and doesn't require LLM power (mostly deterministic: compare CI config files against repo structure).

6. Watch mode / continuous development.
Listed as future in the architecture but never planned. A file-system watcher that triggers incremental scans on save would transform Sentinel from "overnight batch tool" to "background development companion." This meaningfully changes the product positioning — arguably too far from "morning report" toward "ambient awareness."

Tier 3: Ecosystem and distribution plays
7. The copier template as a separate product.
The autonomous builder workflow you extracted is arguably as interesting as Sentinel itself. A reusable template for "vision-locked, checkpoint-driven, autonomous agent development" has broad applicability. The project history is evidence that the workflow works.

8. Team mode / shared findings.
Currently single-user, single-machine. A shared SQLite DB or a lightweight sync layer would let a team share suppressions, approvals, and finding history. This is a significant scope expansion — it turns a personal tool into a team tool — but it's where adoption compounds.

9. Plugin marketplace / community detectors.
The entry-points plugin system (ADR-012) is built. The detectors_dir config and __init_subclass__ auto-registration make adding detectors trivial. What's missing is a discovery mechanism: a registry, a showcase, or even just a sentinel install-detector command that pulls from a known repo. This is premature until there are users, but the architecture is ready for it.