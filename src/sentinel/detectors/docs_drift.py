"""Docs-drift detector — surfaces stale references, dependency drift, and doc-code inconsistencies."""

from __future__ import annotations

import json
import logging
import os
import re
import tomllib
from pathlib import Path

from sentinel.core.ollama import check_ollama
from sentinel.detectors.base import Detector
from sentinel.models import (
    DetectorContext,
    DetectorTier,
    Evidence,
    EvidenceType,
    Finding,
    Severity,
)

logger = logging.getLogger(__name__)

# ── Markdown parsing patterns ──────────────────────────────────────

# [text](path) — markdown links. Capture the link target.
_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

# Inline code paths: `path/to/something.ext` or `src/something`
_INLINE_CODE_PATH = re.compile(r"`([a-zA-Z0-9_./-]+(?:\.[a-zA-Z0-9]+)?)`")

# Fenced code blocks: ```lang\n...\n```
_FENCED_BLOCK = re.compile(r"^```(\w*)\s*\n(.*?)^```", re.MULTILINE | re.DOTALL)

# pip install commands inside code blocks
_PIP_INSTALL = re.compile(r"pip\s+install\s+(.+)", re.IGNORECASE)

# npm install commands inside code blocks
_NPM_INSTALL = re.compile(r"npm\s+install\s+(.+)", re.IGNORECASE)

# Skip directories
_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "__pycache__", "node_modules",
    ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "dist", "build", ".egg-info", ".sentinel",
})

# Template/example path patterns to ignore
_TEMPLATE_PATH_PARTS = frozenset({
    "path", "to", "your", "example", "sample", "placeholder",
})


def _is_template_path(path: str) -> bool:
    """Check if a path looks like a template/example placeholder."""
    lower = path.lower().replace("\\", "/")
    parts = set(lower.split("/"))
    # If the path contains generic placeholder words, it's likely a template
    if len(parts & _TEMPLATE_PATH_PARTS) >= 2:
        return True
    # Check for variable placeholders like {var}, <var>, $var, or -N-/-NNN- patterns
    return bool(re.search(r"(?:\{[^}]+\}|<[^>]+>|\$[A-Za-z]|-N(?:NN)?-|-N(?:NN)?\.)", path))


class DocsDriftDetector(Detector):
    """Detect documentation inconsistencies: stale references, dependency drift."""

    @property
    def name(self) -> str:
        return "docs-drift"

    @property
    def description(self) -> str:
        return "Detect stale references and dependency drift in documentation"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.LLM_ASSISTED

    @property
    def categories(self) -> list[str]:
        return ["docs-drift"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        try:
            return self._scan(context)
        except Exception:
            logger.exception("docs-drift detector failed")
            return []

    def _scan(self, context: DetectorContext) -> list[Finding]:
        repo_root = Path(context.repo_root)
        findings: list[Finding] = []

        md_files = self._get_markdown_files(context, repo_root)
        for md_file in md_files:
            try:
                content = md_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            rel_path = str(md_file.relative_to(repo_root))

            # Stale reference detection
            findings.extend(self._check_stale_references(content, rel_path, repo_root))

            # Dependency drift detection (only for README / CONTRIBUTING / install docs)
            basename = md_file.name.upper()
            is_key_doc = basename in (
                "README.MD", "CONTRIBUTING.MD", "INSTALL.MD", "GETTING-STARTED.MD",
            )
            if is_key_doc:
                findings.extend(self._check_dependency_drift(content, rel_path, repo_root))

            # LLM-assisted doc-code comparison (only for key docs, when available)
            if is_key_doc and not context.config.get("skip_llm"):
                findings.extend(
                    self._check_doc_code_drift(content, rel_path, repo_root, context.config)
                )

        return findings

    # ── File discovery ─────────────────────────────────────────────

    def _get_markdown_files(
        self, context: DetectorContext, repo_root: Path
    ) -> list[Path]:
        if context.scope.value == "targeted" and context.target_paths:
            return [
                repo_root / p
                for p in context.target_paths
                if (repo_root / p).is_file() and p.endswith(".md")
            ]
        if context.scope.value == "incremental" and context.changed_files:
            return [
                repo_root / p
                for p in context.changed_files
                if (repo_root / p).is_file() and p.endswith(".md")
            ]
        return list(self._walk_markdown(repo_root))

    @staticmethod
    def _walk_markdown(root: Path) -> list[Path]:
        results: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                if fname.lower().endswith(".md"):
                    results.append(Path(dirpath) / fname)
        return results

    # ── Stale reference detection ──────────────────────────────────

    def _check_stale_references(
        self, content: str, doc_path: str, repo_root: Path
    ) -> list[Finding]:
        findings: list[Finding] = []
        doc_dir = (repo_root / doc_path).parent
        lines = content.splitlines()

        for line_num, line in enumerate(lines, start=1):
            for match in _MD_LINK.finditer(line):
                link_text = match.group(1)
                link_target = match.group(2)

                finding = self._check_link_target(
                    link_target, link_text, doc_path, doc_dir, repo_root, line_num, line,
                )
                if finding:
                    findings.append(finding)

            # Check inline code paths (only in non-code-block lines)
            if not line.strip().startswith("```"):
                for match in _INLINE_CODE_PATH.finditer(line):
                    path_text = match.group(1)
                    finding = self._check_inline_path(
                        path_text, doc_path, repo_root, line_num, line,
                    )
                    if finding:
                        findings.append(finding)

        return findings

    def _check_link_target(
        self,
        target: str,
        link_text: str,
        doc_path: str,
        doc_dir: Path,
        repo_root: Path,
        line_num: int,
        line: str,
    ) -> Finding | None:
        # Skip external URLs
        if target.startswith(("http://", "https://", "mailto:", "ftp://", "#")):
            return None

        # Strip anchor fragments for file existence check
        file_part = target.split("#")[0]
        if not file_part:
            return None  # Pure anchor link like (#section)

        # Skip obvious template/example paths
        if _is_template_path(file_part):
            return None

        # Try resolving relative to the document's directory (standard markdown)
        resolved_doc_rel = (doc_dir / file_part).resolve()
        # Also try resolving relative to repo root (common GitHub convention)
        resolved_repo_rel = (repo_root / file_part).resolve()

        repo_resolved = repo_root.resolve()

        # Check both resolution strategies — if either finds the file, it's valid
        for resolved in (resolved_doc_rel, resolved_repo_rel):
            try:
                resolved.relative_to(repo_resolved)
            except ValueError:
                continue  # Outside repo, skip this resolution
            if resolved.exists():
                return None  # Link is valid via this resolution strategy

        # Neither resolution found the file — report as stale
        # Use the repo-root relative path for the error message if possible
        try:
            rel_target = str(resolved_doc_rel.relative_to(repo_resolved))
        except ValueError:
            rel_target = file_part

        return Finding(
            detector=self.name,
            category="docs-drift",
            severity=Severity.MEDIUM,
            confidence=0.95,
            title=f"Stale link: [{link_text}]({target})",
            description=(
                f"Documentation {doc_path}:{line_num} links to `{target}` "
                f"but the path does not exist (checked relative to document and repo root)."
            ),
            evidence=[
                Evidence(
                    type=EvidenceType.DOC,
                    source=doc_path,
                    content=line.strip(),
                    line_range=(line_num, line_num),
                ),
            ],
            file_path=doc_path,
            line_start=line_num,
            line_end=line_num,
            context={"pattern": "stale-reference", "target": target, "resolved": rel_target},
        )

    def _check_inline_path(
        self,
        path_text: str,
        doc_path: str,
        repo_root: Path,
        line_num: int,
        line: str,
    ) -> Finding | None:
        # Only check things that look like relative file paths
        # Must contain at least one / and an extension, or start with a known prefix
        if "/" not in path_text:
            return None
        # Skip things that are clearly not paths
        if path_text.startswith(("http://", "https://", "//", "#")):
            return None
        # Must look like a specific file (not a glob or variable)
        if any(c in path_text for c in "*?{}$<>"):
            return None
        # Skip template/example paths
        if _is_template_path(path_text):
            return None

        resolved = (repo_root / path_text).resolve()
        # Safety: only check within repo
        try:
            resolved.relative_to(repo_root.resolve())
        except ValueError:
            return None

        if resolved.exists():
            return None

        return Finding(
            detector=self.name,
            category="docs-drift",
            severity=Severity.LOW,
            confidence=0.80,
            title=f"Stale path reference: `{path_text}`",
            description=(
                f"Documentation {doc_path}:{line_num} references `{path_text}` "
                f"but the path does not exist in the repository."
            ),
            evidence=[
                Evidence(
                    type=EvidenceType.DOC,
                    source=doc_path,
                    content=line.strip(),
                    line_range=(line_num, line_num),
                ),
            ],
            file_path=doc_path,
            line_start=line_num,
            line_end=line_num,
            context={"pattern": "stale-inline-path", "referenced_path": path_text},
        )

    # ── Dependency drift detection ─────────────────────────────────

    def _check_dependency_drift(
        self, content: str, doc_path: str, repo_root: Path
    ) -> list[Finding]:
        findings: list[Finding] = []

        # Extract packages mentioned in install commands within code blocks
        doc_packages = self._extract_doc_packages(content)
        if not doc_packages:
            return findings

        # Get actual project dependencies
        actual_deps = self._get_actual_dependencies(repo_root)
        if not actual_deps:
            return findings  # Can't compare if we don't know real deps

        # Find packages mentioned in docs but not in actual deps
        doc_set = {self._normalize_pkg(p) for p in doc_packages}
        actual_set = {self._normalize_pkg(p) for p in actual_deps}

        # Only report doc-mentioned packages missing from project deps
        # (the reverse — deps not in docs — is less actionable)
        missing_from_project = doc_set - actual_set
        # Filter out obvious non-packages (the project itself, common false positives)
        project_name = self._get_project_name(repo_root)
        skip_names = {".", "-e", "e", "e.", "./", project_name}
        missing_from_project -= {self._normalize_pkg(s) for s in skip_names}

        for pkg in sorted(missing_from_project):
            if not pkg or len(pkg) < 2:
                continue
            findings.append(
                Finding(
                    detector=self.name,
                    category="docs-drift",
                    severity=Severity.MEDIUM,
                    confidence=0.90,
                    title=f"Dependency drift: `{pkg}` in docs but not in project",
                    description=(
                        f"Documentation {doc_path} mentions installing `{pkg}` "
                        f"but it is not listed in the project's dependency files."
                    ),
                    evidence=[
                        Evidence(
                            type=EvidenceType.DOC,
                            source=doc_path,
                            content=f"Package `{pkg}` found in install instructions",
                        ),
                    ],
                    file_path=doc_path,
                    context={"pattern": "dependency-drift", "package": pkg},
                )
            )

        return findings

    def _extract_doc_packages(self, content: str) -> list[str]:
        """Extract package names from pip/npm install commands in code blocks."""
        packages: list[str] = []

        for block_match in _FENCED_BLOCK.finditer(content):
            block_content = block_match.group(2)
            for line in block_content.splitlines():
                line = line.strip()
                # pip install
                pip_match = _PIP_INSTALL.search(line)
                if pip_match:
                    packages.extend(self._parse_install_args(pip_match.group(1)))
                # npm install
                npm_match = _NPM_INSTALL.search(line)
                if npm_match:
                    packages.extend(self._parse_install_args(npm_match.group(1)))

        return packages

    @staticmethod
    def _parse_install_args(args_str: str) -> list[str]:
        """Parse package names from an install command's arguments."""
        packages: list[str] = []
        for token in args_str.split():
            # Skip flags
            if token.startswith("-"):
                continue
            # Strip surrounding quotes
            token = token.strip("\"'")
            # Strip version specifiers
            name = re.split(r"[>=<\[!~]", token)[0].strip()
            if name and name != ".":
                packages.append(name)
        return packages

    def _get_actual_dependencies(self, repo_root: Path) -> set[str]:
        """Collect dependencies from project definition files."""
        deps: set[str] = set()

        # pyproject.toml
        pyproject = repo_root / "pyproject.toml"
        if pyproject.exists():
            deps.update(self._parse_pyproject_deps(pyproject))

        # requirements.txt
        req_txt = repo_root / "requirements.txt"
        if req_txt.exists():
            deps.update(self._parse_requirements_txt(req_txt))

        # package.json
        pkg_json = repo_root / "package.json"
        if pkg_json.exists():
            deps.update(self._parse_package_json(pkg_json))

        return deps

    @staticmethod
    def _parse_pyproject_deps(path: Path) -> set[str]:
        """Extract dependency names from pyproject.toml using stdlib tomllib."""
        deps: set[str] = set()
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError):
            return deps

        # Main dependencies
        for dep_str in data.get("project", {}).get("dependencies", []):
            name = re.split(r"[>=<\[!~;]", dep_str)[0].strip()
            if name:
                deps.add(name)

        # Optional dependencies (all groups)
        optional = data.get("project", {}).get("optional-dependencies", {})
        for group_deps in optional.values():
            for dep_str in group_deps:
                name = re.split(r"[>=<\[!~;]", dep_str)[0].strip()
                if name:
                    deps.add(name)

        return deps

    @staticmethod
    def _parse_requirements_txt(path: Path) -> set[str]:
        deps: set[str] = set()
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                name = re.split(r"[>=<\[!~;@]", line)[0].strip()
                if name:
                    deps.add(name)
        except OSError:
            pass
        return deps

    @staticmethod
    def _parse_package_json(path: Path) -> set[str]:
        deps: set[str] = set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                if key in data and isinstance(data[key], dict):
                    deps.update(data[key].keys())
        except (OSError, json.JSONDecodeError):
            pass
        return deps

    @staticmethod
    def _get_project_name(repo_root: Path) -> str:
        """Get the project name from pyproject.toml if available."""
        pyproject = repo_root / "pyproject.toml"
        if pyproject.exists():
            try:
                with open(pyproject, "rb") as f:
                    data = tomllib.load(f)
                return data.get("project", {}).get("name", "")
            except (OSError, tomllib.TOMLDecodeError):
                pass
        return ""

    @staticmethod
    def _normalize_pkg(name: str) -> str:
        """Normalize a package name for comparison (PEP 503)."""
        return re.sub(r"[-_.]+", "-", name).lower().strip()

    # ── LLM-assisted doc-code comparison ───────────────────────────

    def _check_doc_code_drift(
        self, content: str, doc_path: str, repo_root: Path, config: dict
    ) -> list[Finding]:
        """Use LLM to compare code blocks in docs against actual source files."""
        ollama_url = config.get("ollama_url", "http://localhost:11434")
        model = config.get("model", "qwen3:4b")

        if not check_ollama(ollama_url):
            return []

        findings: list[Finding] = []
        pairs = self._extract_doc_code_pairs(content, doc_path, repo_root)

        for doc_block, code_path, code_content, line_num in pairs:
            try:
                result = self._llm_compare(
                    doc_block, doc_path, code_path, code_content, model, ollama_url
                )
                if result and not result.get("is_accurate", True):
                    issue = result.get("issue", "Documentation may not match implementation")
                    findings.append(
                        Finding(
                            detector=self.name,
                            category="docs-drift",
                            severity=Severity.LOW,
                            confidence=0.65,
                            title=f"Doc-code drift: {doc_path} vs {code_path}",
                            description=(
                                f"LLM comparison found potential drift between documentation "
                                f"in {doc_path} and source code in {code_path}: {issue}"
                            ),
                            evidence=[
                                Evidence(
                                    type=EvidenceType.DOC,
                                    source=doc_path,
                                    content=doc_block[:500],
                                    line_range=(line_num, line_num),
                                ),
                                Evidence(
                                    type=EvidenceType.CODE,
                                    source=code_path,
                                    content=code_content[:500],
                                ),
                            ],
                            file_path=doc_path,
                            line_start=line_num,
                            context={
                                "pattern": "doc-code-drift",
                                "code_path": code_path,
                                "llm_issue": issue,
                            },
                        )
                    )
            except Exception:
                logger.debug("LLM comparison failed for %s block at line %d", doc_path, line_num)

        return findings

    def _extract_doc_code_pairs(
        self, content: str, doc_path: str, repo_root: Path
    ) -> list[tuple[str, str, str, int]]:
        """Extract (doc_block, code_path, code_content, line_num) pairs.

        Looks for code blocks in markdown that reference importable modules or
        CLI commands and tries to find the corresponding source.
        """
        pairs: list[tuple[str, str, str, int]] = []

        for match in _FENCED_BLOCK.finditer(content):
            lang = match.group(1).lower()
            block = match.group(2).strip()
            # Calculate line number of the code block
            line_num = content[:match.start()].count("\n") + 1

            if lang in ("python", "py"):
                # Look for import statements or function calls that reference source files
                referenced = self._find_referenced_source(block, repo_root)
                if referenced:
                    pairs.append((block, referenced[0], referenced[1], line_num))
            elif lang in ("bash", "sh", "shell", "console"):
                # Look for CLI commands that reference the project
                referenced = self._find_cli_source(block, repo_root)
                if referenced:
                    pairs.append((block, referenced[0], referenced[1], line_num))

        return pairs

    @staticmethod
    def _find_referenced_source(
        block: str, repo_root: Path
    ) -> tuple[str, str] | None:
        """Find source file referenced by a Python code block."""
        # Look for import patterns: from X import Y, import X
        imports = re.findall(r"(?:from|import)\s+([\w.]+)", block)
        for imp in imports:
            # Convert module path to file path
            parts = imp.split(".")
            for i in range(len(parts), 0, -1):
                candidate = repo_root / "src" / "/".join(parts[:i])
                py_file = candidate.with_suffix(".py")
                init_file = candidate / "__init__.py"
                for path in (py_file, init_file):
                    if path.exists():
                        try:
                            content = path.read_text(encoding="utf-8", errors="ignore")
                            rel = str(path.relative_to(repo_root))
                            return (rel, content[:2000])
                        except OSError:
                            pass
        return None

    @staticmethod
    def _find_cli_source(
        block: str, repo_root: Path
    ) -> tuple[str, str] | None:
        """Find CLI entry point source for a bash code block."""
        # Resolve the project name dynamically
        project_name = DocsDriftDetector._get_project_name(repo_root)
        if not project_name:
            return None
        # Look for the project's CLI module
        cli_py = repo_root / "src" / project_name / "cli.py"
        if cli_py.exists() and project_name in block:
            try:
                content = cli_py.read_text(encoding="utf-8", errors="ignore")
                rel = str(cli_py.relative_to(repo_root))
                return (rel, content[:2000])
            except OSError:
                pass
        return None

    @staticmethod
    def _llm_compare(
        doc_block: str,
        doc_path: str,
        code_path: str,
        code_content: str,
        model: str,
        ollama_url: str,
    ) -> dict | None:
        """Ask the LLM to compare a doc block against source code."""
        import httpx

        # Use safe string substitution — doc/code content may contain { or }
        prompt = (
            "You are a documentation accuracy checker. Compare the following documentation "
            "code block against the actual source code and determine if the documentation "
            "is accurate.\n\n"
            f"## Documentation (from {doc_path})\n"
            f"```\n{doc_block[:1000]}\n```\n\n"
            f"## Actual source code (from {code_path})\n"
            f"```\n{code_content[:2000]}\n```\n\n"
            "Respond ONLY with a JSON object (no markdown, no explanation):\n"
            '{"is_accurate": true/false, "issue": "One sentence describing the drift if inaccurate, or empty string"}'
        )

        resp = httpx.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 256},
            },
            timeout=60.0,
        )
        resp.raise_for_status()

        data = resp.json()
        text = data.get("response", "").strip()

        # Extract JSON from response
        try:
            # Try to find JSON in the response
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except (json.JSONDecodeError, AttributeError):
            pass

        return None
