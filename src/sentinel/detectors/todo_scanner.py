"""TODO/FIXME/HACK/XXX scanner detector with git blame age."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from datetime import UTC
from pathlib import Path

from sentinel.detectors.base import COMMON_SKIP_DIRS, Detector
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
# Requires a comment prefix (#, //, /*, --, <!--) earlier on the same line
_COMMENT_PREFIX = re.compile(r"(#|//|/\*|^\s*\*|--|<!--)")
# Matches TODO, FIXME, HACK, XXX — non-greedy message capture to allow
# finditer to find multiple tags on the same line.
# Negative lookahead (?!-) rejects compound words like "todo-scanner".
_TODO_PATTERN = re.compile(
    r"\b(TODO|FIXME|HACK|XXX)\b(?!-)(?:\s*[:(]?\s*)(.*?)(?=\b(?:TODO|FIXME|HACK|XXX)\b(?!-)|$)",
    re.IGNORECASE,
)

# Matches TODO/FIXME/HACK/XXX inside HTML comments: <!-- TODO: message -->
_HTML_COMMENT_TODO = re.compile(
    r"<!--\s*\b(TODO|FIXME|HACK|XXX)\b[:\s]*(.*?)\s*-->",
    re.IGNORECASE,
)

# Skip binary / generated files
_SKIP_EXTENSIONS = frozenset({
    ".pyc", ".pyo", ".so", ".o", ".a", ".dll", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".gz", ".tar", ".bz2", ".7z",
    ".db", ".sqlite", ".sqlite3",
    ".lock",
    # Documentation files: # and * are formatting, not comment syntax.
    # HTML comment TODOs in markdown are handled by _scan_markdown_todos().
    ".md", ".rst", ".adoc",
})

# Markdown/documentation extensions — scanned only for HTML comment TODOs
_MARKDOWN_EXTENSIONS = frozenset({".md", ".rst", ".adoc", ".html", ".htm"})

_SKIP_DIRS = COMMON_SKIP_DIRS


def _is_in_string_literal(line: str, prefix: str) -> bool:
    """Heuristic: check if a comment marker is likely inside a string literal.

    Counts unescaped quote characters before the comment marker.
    If the number of quotes is odd, the marker is inside a string.
    """
    # Count unescaped single and double quotes in the prefix
    for quote in ('"', "'"):
        count = 0
        i = 0
        while i < len(prefix):
            if prefix[i] == "\\" and i + 1 < len(prefix):
                i += 2  # skip escaped char
                continue
            if prefix[i] == quote:
                count += 1
            i += 1
        if count % 2 == 1:
            return True
    return False


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
                for match in _TODO_PATTERN.finditer(line):
                    # Only count if the tag appears in a comment context
                    tag_start = match.start()
                    prefix = line[:tag_start]
                    # Find ALL comment markers in the prefix, use the LAST (nearest) one
                    comment_matches = list(_COMMENT_PREFIX.finditer(prefix))
                    if not comment_matches:
                        continue
                    nearest_comment = comment_matches[-1]
                    # Skip if the nearest comment marker is inside a string literal
                    if _is_in_string_literal(line, prefix):
                        continue
                    # Require the TODO tag to be near the comment marker.
                    # "# TODO: fix" → ok.  "# Should find TODOs" → skip.
                    chars_after_comment = tag_start - nearest_comment.end()
                    if chars_after_comment > 5:
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

        # Also scan markdown files for HTML comment TODOs
        md_files = self._get_markdown_files(context, repo_root)
        findings.extend(self._scan_markdown_todos(repo_root, md_files))

        return findings

    def _get_files(
        self, context: DetectorContext, repo_root: Path
    ) -> list[Path]:
        """Get the list of code files to scan based on scope."""
        if context.scope.value == "targeted" and context.target_paths:
            return [
                repo_root / p
                for p in context.target_paths
                if (repo_root / p).is_file()
                and (repo_root / p).suffix.lower() not in _SKIP_EXTENSIONS
            ]
        if context.scope.value == "incremental" and context.changed_files:
            return [
                repo_root / p
                for p in context.changed_files
                if (repo_root / p).is_file()
                and (repo_root / p).suffix.lower() not in _SKIP_EXTENSIONS
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

    def _get_markdown_files(
        self, context: DetectorContext, repo_root: Path
    ) -> list[Path]:
        """Get markdown/doc files to scan for HTML comment TODOs."""
        if context.scope.value == "targeted" and context.target_paths:
            return [
                repo_root / p
                for p in context.target_paths
                if (repo_root / p).is_file()
                and (repo_root / p).suffix.lower() in _MARKDOWN_EXTENSIONS
            ]
        if context.scope.value == "incremental" and context.changed_files:
            return [
                repo_root / p
                for p in context.changed_files
                if (repo_root / p).is_file()
                and (repo_root / p).suffix.lower() in _MARKDOWN_EXTENSIONS
            ]
        results: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(repo_root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                fpath = Path(dirpath) / fname
                if fpath.suffix.lower() in _MARKDOWN_EXTENSIONS:
                    results.append(fpath)
        return results

    def _scan_markdown_todos(
        self, repo_root: Path, files: list[Path]
    ) -> list[Finding]:
        """Scan markdown files for TODO tags inside HTML comments."""
        findings: list[Finding] = []
        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            for line_num, line in enumerate(content.splitlines(), start=1):
                for match in _HTML_COMMENT_TODO.finditer(line):
                    tag = match.group(1).upper()
                    message = match.group(2).strip() or "(no description)"
                    rel_path = str(file_path.relative_to(repo_root))

                    blame_info = self._git_blame_line(
                        repo_root, rel_path, line_num
                    )

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

                    findings.append(
                        Finding(
                            detector=self.name,
                            category="todo-fixme",
                            severity=self._tag_severity(tag),
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
                from datetime import datetime

                try:
                    ts = datetime.fromtimestamp(int(author_time), tz=UTC)
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
