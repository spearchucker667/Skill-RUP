"""
Data models and type definitions for RUP deterministic runtime.
"""
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
import hashlib
import datetime

@dataclass
class RepoMetadata:
    name: str
    primary_language: str
    repo_type: str = "application"
    loc: int = 0
    file_count: int = 0
    contributors: int = 1
    last_commit: str = ""
    open_issues: int = 0
    license: str = "UNKNOWN"

@dataclass
class LanguageEntry:
    name: str
    percentage: float
    lockfile_present: bool = False

@dataclass
class Gap:
    id: str
    category: str
    severity: str  # critical, high, medium, low
    title: str
    description: str
    impact: str
    suggested_fix: str
    effort_estimate: str  # small, medium, large
    files_affected: List[str] = field(default_factory=list)

@dataclass
class RiskFactor:
    factor: str
    severity: str
    mitigation: str

@dataclass
class RiskAssessment:
    overall_risk: str = "low"
    technical_debt_score: int = 0
    production_readiness_score: int = 100
    risk_factors: List[Dict[str, str]] = field(default_factory=list)

@dataclass
class Scope:
    files: List[str] = field(default_factory=list)
    packages: List[str] = field(default_factory=list)

@dataclass
class BacklogItem:
    id: str
    priority: str  # P0, P1, P2, P3
    category: str
    title: str
    description: str
    scope: Scope
    risk: str  # low, medium, high
    estimated_effort_minutes: int
    verification_method: str
    dependencies: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)

@dataclass
class ExecutionChange:
    file_path: str
    change_type: str  # create, modify, delete, rename
    rationale: str
    backlog_item_id: str

@dataclass
class ExecutionCommit:
    hash: str
    message: str
    files: List[str] = field(default_factory=list)
    type: str = "commit"
    breaking: bool = False
    backlog_item_ids: List[str] = field(default_factory=list)

@dataclass
class RunManifest:
    run_id: str
    created_at: str
    protocol_version: str = "3.0.0"
    canonical_commit: str = "c3d6f70375db15d53db2fba76d70b5b7c9cf98bb"
    target_path: str = ""
    target_commit: str = ""
    phases_completed: List[str] = field(default_factory=list)
    selected_items: List[str] = field(default_factory=list)
    execution_changes_count: int = 0
    verification_status: str = "pending"

    @staticmethod
    def generate_run_id(target_path: str = "") -> str:
        """Generate a deterministic run ID from canonical constants and the target path.

        The result is stable for the same target path, satisfying the deterministic
        run-ID contract in SKILL.md.
        """
        canonical = (
            f"{RunManifest.protocol_version}:"
            f"{RunManifest.canonical_commit}:"
            f"{target_path}"
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        return f"rup-{digest}"

@dataclass
class SessionState:
    run_id: str
    current_phase: str
    updated_at: str
    artifacts_generated: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

