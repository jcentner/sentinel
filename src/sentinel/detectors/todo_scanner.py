"""TODO/FIXME/HACK/XXX scanner detector with git blame age."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path

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

# Matches TODO, FIXME, HACK, XXX after a comment marker
# Requires a comment prefix (#, //, /*, *, --, <!--) earlier on the same line
_COMMENT_PREFIX = re.compile(r"(#|//|/\*|\*|--|<!--|%|;)")
_TODO_PATTERN = re.compile(
    r"\b(TODO|FIXME|HACK|XXX)\s*[:(]?\s*(.*)", re.IGNORECASE
)

# Skip binary / generated files
_SKIP_EXTENSIONS = frozenset({
    ".pyc", ".pyo", ".so", ".o", ".a", ".dll", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".gz", ".tar", ".bz2", ".7z",
    ".db", ".sqlite", ".sqlite3",
    ".lock",
})

_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "__pycache__", "node_modules",
    ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "dist", "build", ".egg-info",
})


class TodoScanner(Detector):
    """Scan for TODO/FIXME/HACK/XXX comments with optional git blame age."""

    @property
    def name(self) -> str:
        return "todo-scanner"

    @property
    def description(self) -> str:
        return "Grep for TODO/FIXME/HACK/XXX comments with age from git blame"

    @property
    def tier(self) -> DetectorTier:
        return DetectorTier.DETERMINISTIC

    @property
    def categories(self) -> list[str]:
        return ["todo-fixme"]

    def detect(self, context: DetectorContext) -> list[Finding]:
        try:
            return self._scan(context)
        except Exception:
            logger.exception("todo-scanner failed")
            return []

    def _scan(self, context: DetectorContext) -> list[Finding]:
        repo_root = Path(context.repo_root)
        findings: list[Finding] = []

        files = self._get_files(context, repo_root)
        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            for line_num, line in enumerate(content.splitlines(), start=1):
                match = _TODO_PATTERN.search(line)
                if not match:
                    continue
                # Only count if the tag appears in a comment context
                tag_start = match.start()
                prefix = line[:tag_start]
                if not _COMMENT_PREFIX.search(prefix):
                    continue
                tag = match.group(1).upper()
                message = match.group(2).strip() or "(no description)"
                rel_path = str(file_path.relative_to(repo_root))

                blame_info = self._git_blame_line(repo_root, rel_path, line_num)

                evidence = [
                    Evidence(
                        type=EvidenceType.CODE,
                        source=rel_path,
                        content=line.strip(),
                        line_range=(line_num, line_num),
                    )
                ]
                if blame_info:
                    evidence.append(
                        Evidence(
                            type=EvidenceType.GIT_HISTORY,
                            source=rel_path,
                            content=blame_info,
                        )
                    )

                severity = self._tag_severity(tag)

                findings.append(
                    Finding(
                        detector=self.name,
                        category="todo-fixme",
                        severity=severity,
                        confidence=0.9,
                        title=f"{tag}: {message[:80]}",
                        description=f"{tag} comment in {rel_path}:{line_num} — {message}",
                        evidence=evidence,
                        file_path=rel_path,
                        line_start=line_num,
                        line_end=line_num,
                        context={"tag": tag, "blame": blame_info},
                    )
                )

        return findings

    def _get_files(
        self, context: DetectorContext, repo_root: Path
    ) -> list[Path]:
        """Get the list of files to scan based on scope."""
        if context.scope.value == "targeted" and context.target_paths:
            return [
                repo_root / p
                for p in context.target_paths
                if (repo_root / p).is_file()
            ]
        if context.scope.value == "incremental" and context.changed_files:
            return [
                repo_root / p
                for p in context.changed_files
                if (repo_root / p).is_file()
            ]
        return list(self._walk_files(repo_root))

    def _walk_files(self, root: Path) -> list[Path]:
        """Walk the repo tree, skipping binary and generated files."""
        results: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            # Remove skip dirs in-place to avoid descending
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

            for fname in filenames:
                fpath = Path(dirpath) / fname
                if fpath.suffix.lower() in _SKIP_EXTENSIONS:
                    continue
                results.append(fpath)
        return results

    @staticmethod
    def _git_blame_line(
        repo_root: Path, rel_path: str, line_num: int
    ) -> str | None:
        """Run git blame on a single line and return the commit info string."""
        try:
            result = subprocess.run(
                [
                    "git", "blame", "-L", f"{line_num},{line_num}",
                    "--porcelain", "--", rel_path,
                ],
                capture_output=True,
                text=True,
                cwd=str(repo_root),
                timeout=10,
            )
            if result.returncode != 0:
                return None
            # Extract author-time from porcelain output
            lines = result.stdout.splitlines()
            author = ""
            author_time = ""
            for blame_line in lines:
                if blame_line.startswith("author "):
                    author = blame_line[len("author "):]
                elif blame_line.startswith("author-time "):
                    author_time = blame_line[len("author-time "):]

            if author and author_time:
                from datetime import datetime, timezone

                try:
                    ts = datetime.fromtimestamp(int(author_time), tz=timezone.utc)
                    return f"Added by {author} on {ts.strftime('%Y-%m-%d')}"
                except (ValueError, OSError):
                    return f"Added by {author}"
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    @staticmethod
    def _tag_severity(tag: str) -> Severity:
        """Map TODO tag to severity level."""
        if tag in ("HACK", "XXX"):
            return Severity.HIGH
        if tag == "FIXME":
            return Severity.MEDIUM
        return Severity.LOW
