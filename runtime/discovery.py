"""
discovery module for RUP deterministic runtime.
"""
from typing import Dict, Any
from pathlib import Path
from .inventory import InventoryManager
from .state import StateManager
from .artifact_builder import ArtifactBuilder

class DiscoveryPhase:
    def __init__(self, target_dir: Path, state_manager: StateManager, artifact_builder: ArtifactBuilder):
        self.inventory = InventoryManager(target_dir)
        self.state_manager = state_manager
        self.artifact_builder = artifact_builder
        self.target_dir = target_dir

    def _evaluate_gaps(self, languages, tooling, metadata) -> list:
        gaps = []
        # Check Tests
        if "test_framework" not in tooling:
            gaps.append({
                "id": "TEST-001",
                "category": "tests",
                "severity": "high",
                "title": "Missing Test Framework",
                "description": "No recognized test framework (e.g. pytest, jest) detected.",
                "impact": "Code correctness cannot be verified.",
                "suggested_fix": f"Install and configure test framework for {metadata.get('primary_language', 'project')}.",
                "effort_estimate": "medium",
                "files_affected": []
            })
            
        # Check CI
        has_ci = list(self.target_dir.glob(".github/workflows/*.yml")) or list(self.target_dir.glob(".gitlab-ci.yml"))
        if not has_ci:
            gaps.append({
                "id": "CI-001",
                "category": "ci",
                "severity": "high",
                "title": "Missing CI/CD Pipeline",
                "description": "No GitHub Actions or GitLab CI configuration found.",
                "impact": "No automated checks for PRs.",
                "suggested_fix": "Add basic CI pipeline for linting and testing.",
                "effort_estimate": "small",
                "files_affected": []
            })
            
        # Check Docs
        if not (self.target_dir / "README.md").exists():
            gaps.append({
                "id": "DOCS-001",
                "category": "docs",
                "severity": "medium",
                "title": "Missing README.md",
                "description": "Project lacks a primary README document.",
                "impact": "Poor developer experience and onboarding.",
                "suggested_fix": "Generate standard README.md.",
                "effort_estimate": "small",
                "files_affected": ["README.md"]
            })
            
        return gaps
        
    def _calculate_risk(self, gaps, metadata) -> dict:
        severity_score = sum(3 if g['severity'] == 'critical' else 2 if g['severity'] == 'high' else 1 for g in gaps)
        
        overall = "low"
        if severity_score > 5:
            overall = "high"
        elif severity_score > 2:
            overall = "medium"
            
        debt = min(100, severity_score * 10)
        readiness = max(0, 100 - debt)
        
        return {
            "overall_risk": overall,
            "technical_debt_score": debt,
            "production_readiness_score": readiness
        }

    def execute(self) -> Dict[str, Any]:
        """Run the discovery phase and generate the discovery report."""
        languages = self.inventory.detect_languages()
        tooling = self.inventory.detect_tooling(languages)
        metadata = self.inventory.get_repo_metadata()
        
        gaps = self._evaluate_gaps(languages, tooling, metadata)
        risk = self._calculate_risk(gaps, metadata)
        
        discovery_data = {
            "repo_metadata": metadata,
            "languages": languages,
            "tooling": tooling,
            "gaps": gaps,
            "risk_assessment": risk
        }

        # Save machine-readable state
        self.state_manager.save_json(discovery_data, "RUP_DISCOVERY.json")
        
        # Build human-readable markdown
        self.artifact_builder.build_markdown("discovery-report.md", discovery_data, "RUP_DISCOVERY.md")
        
        return discovery_data
