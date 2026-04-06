"""Core data models for Sentinel findings, evidence, and run context."""

from __future__ import annotations

import enum
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


class Severity(str, enum.Enum):
    """Finding severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EvidenceType(str, enum.Enum):
    """Types of supporting evidence."""

    CODE = "code"
    DOC = "doc"
    TEST = "test"
    CONFIG = "config"
    GIT_HISTORY = "git_history"
    LINT_OUTPUT = "lint_output"
    AUDIT_OUTPUT = "audit_output"
    DIFF = "diff"


class FindingStatus(str, enum.Enum):
    """Lifecycle status of a finding."""

    NEW = "new"
    CONFIRMED = "confirmed"
    SUPPRESSED = "suppressed"
    RESOLVED = "resolved"
    APPROVED = "approved"


class ScopeType(str, enum.Enum):
    """Scan scope types."""

    FULL = "full"
    INCREMENTAL = "incremental"
    TARGETED = "targeted"


class DetectorTier(str, enum.Enum):
    """Detector classification tiers."""

    DETERMINISTIC = "deterministic"
    HEURISTIC = "heuristic"
    LLM_ASSISTED = "llm-assisted"


@dataclass(frozen=True)
class Evidence:
    """A piece of supporting evidence for a finding."""

    type: EvidenceType
    source: str
    content: str
    line_range: tuple[int, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Evidence:
        return cls(
            type=EvidenceType(data["type"]),
            source=data["source"],
            content=data["content"],
            line_range=tuple(data["line_range"]) if data.get("line_range") else None,
        )


@dataclass
class Finding:
    """A single issue detected by a detector."""

    detector: str
    category: str
    severity: Severity
    confidence: float
    title: str
    description: str
    evidence: list[Evidence]
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    context: dict[str, Any] | None = None
    fingerprint: str = ""
    status: FindingStatus = FindingStatus.NEW
    id: int | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be 0.0–1.0, got {self.confidence}")
        if not isinstance(self.severity, Severity):
            self.severity = Severity(self.severity)
        if not isinstance(self.status, FindingStatus):
            self.status = FindingStatus(self.status)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["status"] = self.status.value
        d["evidence"] = [e.to_dict() for e in self.evidence]
        d["timestamp"] = self.timestamp.isoformat()
        return d

    def evidence_json(self) -> str:
        return json.dumps([e.to_dict() for e in self.evidence])

    def context_json(self) -> str | None:
        if self.context is None:
            return None
        return json.dumps(self.context)


@dataclass
class DetectorContext:
    """Context provided to each detector during a scan run."""

    repo_root: str
    scope: ScopeType = ScopeType.FULL
    changed_files: list[str] | None = None
    target_paths: list[str] | None = None
    config: dict[str, Any] = field(default_factory=dict)
    # Optional DB connection for structured LLM interaction logging.
    # Set by the runner; detectors that make LLM calls can use these
    # to persist prompt/response/verdict data for analysis.
    conn: Any = None
    run_id: int | None = None


@dataclass
class RunSummary:
    """Summary of a completed scan run."""

    id: int | None = None
    repo_path: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    scope: ScopeType = ScopeType.FULL
    finding_count: int = 0
    commit_sha: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "repo_path": self.repo_path,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "scope": self.scope.value,
            "finding_count": self.finding_count,
            "commit_sha": self.commit_sha,
        }
