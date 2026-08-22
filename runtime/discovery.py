"""
Discovery phase module for RUP deterministic runtime.
Implements canonical Phase 1 Discovery:
1.1 Repository Inventory
1.2 Tooling Detection
1.3 Quality Assessment
1.4 Security Assessment
1.5 Documentation Assessment
1.6 Governance Assessment
1.7 Gap Analysis & Risk Scoring
"""
from typing import Dict, Any, List
from pathlib import Path
from .inventory import InventoryManager, LOCKFILES
from .tool_detection import ToolDetector
from .redaction import scan_file_for_secrets
from .security import iter_jailed_files, scan_content_for_threats
from .state import StateManager
from .artifact_builder import ArtifactBuilder
from .workspace import changed_packages, dependency_order, detect_workspace

class DiscoveryPhase:
    def __init__(self, target_dir: Path, state_manager: StateManager, artifact_builder: ArtifactBuilder):
        self.target_dir = target_dir
        self.state_manager = state_manager
        self.artifact_builder = artifact_builder
        self.inventory_mgr = InventoryManager(target_dir)
        self.tool_detector = ToolDetector(target_dir)

    def _evaluate_all_gaps(self, metadata: Dict[str, Any], languages: List[Dict[str, Any]], tooling: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Evaluate gaps across all 6 canonical assessment dimensions."""
        gaps = []
        primary_lang = metadata.get("primary_language", "unknown")

        # --- 1.2 / 1.3 Quality & Testing Gaps ---
        if not tooling.get("test_framework"):
            gaps.append({
                "id": "TEST-001",
                "category": "tests",
                "severity": "high",
                "title": "Missing Test Framework",
                "description": f"No recognized test framework detected for primary language '{primary_lang}'.",
                "impact": "Code correctness, regression prevention, and refactoring safety cannot be verified.",
                "suggested_fix": f"Configure standard test framework (e.g., pytest, jest, or cargo test) for {primary_lang}.",
                "effort_estimate": "medium",
                "files_affected": []
            })

        if not tooling.get("linter"):
            gaps.append({
                "id": "LINT-001",
                "category": "dx",
                "severity": "medium",
                "title": "Missing Linter Configuration",
                "description": f"No linter configuration detected for '{primary_lang}'.",
                "impact": "Inconsistent code style, undetected static code defects, and anti-patterns.",
                "suggested_fix": f"Add linter configuration (e.g. ruff, eslint, or clippy) for {primary_lang}.",
                "effort_estimate": "small",
                "files_affected": []
            })

        if not tooling.get("type_checker") and primary_lang in ("typescript", "python"):
            gaps.append({
                "id": "TYPE-001",
                "category": "dx",
                "severity": "low",
                "title": "Missing Static Type Checking",
                "description": f"No static type checker (mypy/pyright/tsc) configured for {primary_lang}.",
                "impact": "Type errors may manifest at runtime rather than build time.",
                "suggested_fix": f"Configure static type checking (tsconfig.json / mypy.ini) for {primary_lang}.",
                "effort_estimate": "medium",
                "files_affected": []
            })

        # --- 1.4 Security Gaps ---
        # Secret Scanning (jailed walker: repository file symlinks can never pull
        # external content into the scan, RUP-SEC-001).
        secret_findings = []
        skip_dirs = {".git", ".venv", "venv", "node_modules", "dist", "build", ".rup"}
        for p in iter_jailed_files(self.target_dir, skip_dirnames=skip_dirs):
            findings = scan_file_for_secrets(p)
            if findings:
                secret_findings.extend(findings)

        if secret_findings:
            gaps.append({
                "id": "SEC-001",
                "category": "security",
                "severity": "critical",
                "title": f"Exposed Secrets Detected ({len(secret_findings)} findings)",
                "description": "Potential API keys, tokens, or private credentials identified in repository files.",
                "impact": "High risk of credential exposure and unauthorized account access.",
                "suggested_fix": "Revoke exposed credentials, remove secrets from git history, and use environment variables.",
                "effort_estimate": "medium",
                "files_affected": [f.get("file", "") for f in secret_findings[:5]]
            })

        # Lockfile Gap (only for ecosystems with a meaningful lockfile model)
        for idx, lang_info in enumerate(languages):
            lang = lang_info["name"]
            if lang not in LOCKFILES:
                continue
            if lang_info["percentage"] > 10.0 and not lang_info.get("lockfile_present"):
                gaps.append({
                    "id": f"SEC-{100 + idx:03d}",
                    "category": "security",
                    "severity": "high",
                    "title": f"Missing Dependency Lockfile for {lang_info['name'].title()}",
                    "description": f"No lockfile found for {lang_info['name']} dependencies.",
                    "impact": "Non-reproducible builds, vulnerability to dependency confusion and unpinned breaking upstream updates.",
                    "suggested_fix": f"Generate and commit a deterministic lockfile for {lang_info['name']}.",
                    "effort_estimate": "small",
                    "files_affected": []
                })

        # Security Policy
        if not (self.target_dir / "SECURITY.md").exists() and not (self.target_dir / ".github" / "SECURITY.md").exists():
            gaps.append({
                "id": "SEC-003",
                "category": "security",
                "severity": "medium",
                "title": "Missing SECURITY.md Policy",
                "description": "No security disclosure policy found in repository root or .github/.",
                "impact": "Security researchers have no clear channel to responsibly disclose vulnerabilities.",
                "suggested_fix": "Add standard SECURITY.md outlining disclosure policy and contact points.",
                "effort_estimate": "small",
                "files_affected": ["SECURITY.md"]
            })

        # License Compliance
        if metadata.get("license") == "UNKNOWN":
            gaps.append({
                "id": "GOV-002",
                "category": "governance",
                "severity": "high",
                "title": "Missing Open Source License",
                "description": "No recognized LICENSE file found in repository root.",
                "impact": "Default copyright prevents downstream users and automated tools from legally using the code.",
                "suggested_fix": "Add an explicit open source or proprietary license file (e.g. Apache-2.0, MIT).",
                "effort_estimate": "small",
                "files_affected": ["LICENSE"]
            })

        # --- 1.5 Documentation Gaps ---
        if not (self.target_dir / "README.md").exists():
            gaps.append({
                "id": "DOCS-001",
                "category": "docs",
                "severity": "high",
                "title": "Missing README.md",
                "description": "Repository lacks a primary README document.",
                "impact": "Developers and automated agents cannot determine project purpose, setup, or usage.",
                "suggested_fix": "Create structured README.md with overview, installation, usage, and development guide.",
                "effort_estimate": "small",
                "files_affected": ["README.md"]
            })

        if not (self.target_dir / "CONTRIBUTING.md").exists() and not (self.target_dir / ".github" / "CONTRIBUTING.md").exists():
            gaps.append({
                "id": "DOCS-002",
                "category": "docs",
                "severity": "low",
                "title": "Missing CONTRIBUTING.md Guidelines",
                "description": "No contribution guidelines provided for contributors.",
                "impact": "Inconsistent contribution quality and friction during PR reviews.",
                "suggested_fix": "Add CONTRIBUTING.md outlining branch workflow, coding standards, and PR requirements.",
                "effort_estimate": "small",
                "files_affected": ["CONTRIBUTING.md"]
            })

        # --- 1.6 Governance & CI/CD Gaps ---
        if not tooling.get("ci_platform"):
            gaps.append({
                "id": "CI-001",
                "category": "ci",
                "severity": "high",
                "title": "Missing CI/CD Pipeline Automation",
                "description": "No automated CI workflow (GitHub Actions, GitLab CI, CircleCI) detected.",
                "impact": "Pull requests are not automatically validated against tests and linting.",
                "suggested_fix": f"Add CI workflow file to run automated test and lint suites for {primary_lang}.",
                "effort_estimate": "small",
                "files_affected": [".github/workflows/ci.yml"]
            })

        has_codeowners = (self.target_dir / "CODEOWNERS").exists() or (self.target_dir / ".github" / "CODEOWNERS").exists()
        if not has_codeowners:
            gaps.append({
                "id": "GOV-001",
                "category": "governance",
                "severity": "low",
                "title": "Missing CODEOWNERS Specification",
                "description": "No CODEOWNERS file present to designate review responsibilities.",
                "impact": "Unassigned PR reviews and unclear component ownership.",
                "suggested_fix": "Add .github/CODEOWNERS designating team review responsibilities.",
                "effort_estimate": "small",
                "files_affected": [".github/CODEOWNERS"]
            })

        # --- 1.7 Containerization Gaps (ws_containers) ---
        # The canonical Gap category enum (protocol/rup-schema.json) has no
        # containerization/observability slots, so the gaps are classified under
        # the closest canonical dimensions (performance / dx) while their ids
        # (CONT-xxx / OBS-xxx) drive execution subtype routing.
        container_tooling = tooling.get("containerization") or ""
        has_container_definition = bool(container_tooling) or (
            self.target_dir / "Dockerfile"
        ).exists()
        if not has_container_definition:
            gaps.append({
                "id": "CONT-001",
                "category": "performance",
                "severity": "medium",
                "title": "Missing Container Configuration",
                "description": "No Dockerfile/Containerfile or Compose definition detected.",
                "impact": "Application cannot be packaged or deployed reproducibly as a container.",
                "suggested_fix": "Add a multi-stage Dockerfile with pinned dependencies, a non-root runtime user, health checks, and a .dockerignore.",
                "effort_estimate": "medium",
                "files_affected": ["Dockerfile", ".dockerignore"]
            })

        # --- 1.8 Observability Gaps (ws_observability) ---
        has_observability = (self.target_dir / "docs" / "observability.md").exists()
        if not has_observability:
            gaps.append({
                "id": "OBS-001",
                "category": "dx",
                "severity": "low",
                "title": "Missing Observability Baseline",
                "description": "No structured logging, metrics, or tracing baseline documented.",
                "impact": "Runtime issues are hard to diagnose without correlated logs, metrics, and traces.",
                "suggested_fix": "Add an observability baseline: JSON structured logging, standard metrics, OpenTelemetry tracing with W3C Trace Context.",
                "effort_estimate": "small",
                "files_affected": ["docs/observability.md"]
            })

        return gaps

    def _calculate_risk_and_scores(self, gaps: List[Dict[str, Any]], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate technical debt, production readiness, and overall risk levels."""
        weights = {"critical": 30, "high": 15, "medium": 8, "low": 3}
        total_penalty = sum(weights.get(g.get("severity", "low"), 5) for g in gaps)

        debt_score = min(100, total_penalty)
        readiness_score = max(0, 100 - debt_score)

        if any(g.get("severity") == "critical" for g in gaps) or debt_score >= 50:
            overall_risk = "high"
        elif any(g.get("severity") == "high" for g in gaps) or debt_score >= 25:
            overall_risk = "medium"
        else:
            overall_risk = "low"

        risk_factors = []
        for g in gaps:
            if g.get("severity") in ("critical", "high"):
                risk_factors.append({
                    "factor": g.get("title", ""),
                    "severity": g.get("severity", "high"),
                    "mitigation": g.get("suggested_fix", "")
                })

        return {
            "overall_risk": overall_risk,
            "technical_debt_score": debt_score,
            "production_readiness_score": readiness_score,
            "risk_factors": risk_factors
        }

    def execute(self) -> Dict[str, Any]:
        """Run the complete discovery phase and persist machine/human artifacts."""
        inventory_data = self.inventory_mgr.analyze_inventory()
        languages = inventory_data["languages"]
        metadata = self.inventory_mgr.get_repo_metadata()
        tooling = self.tool_detector.detect_all(languages)

        gaps = self._evaluate_all_gaps(metadata, languages, tooling)
        risk_data = self._calculate_risk_and_scores(gaps, metadata)

        # Canonical monorepo field (audit P1-11): the workspace package graph
        # with per-package name/path/language/type, or null for single-package
        # repositories.
        ws = detect_workspace(self.target_dir)
        monorepo = None
        if ws is not None:
            monorepo = {
                "is_monorepo": True,
                "tool": ws["tool"],
                "packages": ws["packages"],
            }

        discovery_report = {
            "repo_metadata": metadata,
            "languages": languages,
            "tooling": {
                k: v for k, v in tooling.items() if v is not None and v != [] and v != {}
            },
            "monorepo": monorepo,
            "gaps": gaps,
            "risk_assessment": risk_data
        }

        # Save machine-readable state atomically
        self.state_manager.save_json(discovery_report, "RUP_DISCOVERY.json")

        # Build human-readable markdown matching canonical template
        self.artifact_builder.build_markdown("discovery-report.md", discovery_report, "RUP_DISCOVERY.md")

        return discovery_report

