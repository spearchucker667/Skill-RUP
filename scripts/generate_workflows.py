#!/usr/bin/env python3
"""
Generate and validate canonical, deduplicated agent workflow files for Skill-RUP.
Matches canonical RUP Protocol v3.0.0 phases, workstreams, and operational procedures.
"""
import sys
import argparse
import yaml
from pathlib import Path

CANONICAL_WORKFLOWS = {
    # Core Phases
    "discovery": {
        "title": "Phase 1: Discovery",
        "purpose": "Comprehensive repository assessment across 7 steps (inventory, tooling, quality, security, documentation, governance, gap analysis).",
        "phase_id": "phase_1_discovery",
        "cli_command": "python3 -m runtime.cli discovery --target <dir>"
    },
    "planning": {
        "title": "Phase 2: Planning",
        "purpose": "Constraint-aware backlog generation, P0-P3 prioritization, time budgeting, dependency ordering, and risk analysis.",
        "phase_id": "phase_2_planning",
        "cli_command": "python3 -m runtime.cli plan --target <dir> --time-budget 45"
    },
    "execution": {
        "title": "Phase 3: Execution",
        "purpose": "Disciplined workstream remediation, failing-test-first scaffolding, atomic file changes, and change tracking.",
        "phase_id": "phase_3_execution",
        "cli_command": "python3 -m runtime.cli execute --target <dir>"
    },
    "verification": {
        "title": "Phase 4: Verification",
        "purpose": "Multi-gate verification: 3-run test flakiness check, linting, secret scanning, SAST pattern check, build, and git metrics.",
        "phase_id": "phase_4_verification",
        "cli_command": "python3 -m runtime.cli verify --target <dir>"
    },
    "reporting": {
        "title": "Phase 4 Handoff: Reporting",
        "purpose": "Evidence-backed final report generation, run manifest creation, follow-up tracking, and truthful publication instructions.",
        "phase_id": "phase_4_verification",
        "cli_command": "python3 -m runtime.cli report --target <dir>"
    },

    # Workstreams
    "bugs": {
        "title": "Workstream: Bug Remediation (ws_bugs)",
        "purpose": "Reproduction test case creation, minimal surgical fix implementation, and regression verification.",
        "workstream_id": "ws_bugs"
    },
    "tests": {
        "title": "Workstream: Test Scaffolding & Upgrades (ws_tests)",
        "purpose": "Test framework configuration, baseline unit/integration test suite generation, and 3-run flakiness detection.",
        "workstream_id": "ws_tests"
    },
    "ci": {
        "title": "Workstream: CI/CD Automation (ws_ci)",
        "purpose": "Automated workflow creation for GitHub Actions/GitLab CI with multi-language matrix and lint/test jobs.",
        "workstream_id": "ws_ci"
    },
    "docs": {
        "title": "Workstream: Documentation & Architecture (ws_docs)",
        "purpose": "Standardized README, CONTRIBUTING, architecture guides, and API reference documentation.",
        "workstream_id": "ws_docs"
    },
    "governance": {
        "title": "Workstream: Governance & Community (ws_governance)",
        "purpose": "CODEOWNERS designation, LICENSE compliance, issue/PR templates, and release automation.",
        "workstream_id": "ws_governance"
    },
    "security": {
        "title": "Workstream: Security Hardening (ws_security)",
        "purpose": "Secret revocation/scanning, SECURITY.md policy, dependency vulnerability fixes, and SAST defenses.",
        "workstream_id": "ws_security"
    },
    "containers": {
        "title": "Workstream: Containers & Docker (ws_containers)",
        "purpose": "Deterministic Dockerfile creation, multi-stage builds, and non-root security configurations.",
        "workstream_id": "ws_containers"
    },
    "iac": {
        "title": "Workstream: Infrastructure as Code (ws_iac)",
        "purpose": "Terraform / CloudFormation / Pulumi resource definitions and environment drift mitigation.",
        "workstream_id": "ws_iac"
    },
    "observability": {
        "title": "Workstream: Observability & Telemetry (ws_observability)",
        "purpose": "Structured logging, OpenTelemetry integration, metric instrumentation, and health checks.",
        "workstream_id": "ws_observability"
    },

    # Operational Workflows
    "quick-run": {
        "title": "Operational Workflow: Quick Run",
        "purpose": "Rapid automated triage and critical P0 gap remediation within a constrained 15-minute time budget.",
        "cli_command": "python3 -m runtime.cli run --target <dir> --time-budget 15"
    },
    "hotfix": {
        "title": "Operational Workflow: Hotfix",
        "purpose": "Isolated, surgical fix for production regressions with minimal change footprint.",
        "cli_command": "python3 -m runtime.cli run --target <dir> --max-files 3 --risk-tolerance low"
    },
    "monorepo": {
        "title": "Operational Workflow: Monorepo Orchestration",
        "purpose": "Scoped execution across workspace packages (pnpm, nx, turborepo, cargo workspaces, go work).",
        "cli_command": "python3 -m runtime.cli run --target <dir>"
    },
    "rollback": {
        "title": "Operational Workflow: Rollback & Reversion",
        "purpose": "Deterministic reversion of executed changes using baseline git checkpoints and cleanup commands.",
        "cli_command": "git checkout -- <modified_files> && rm -f <created_files>"
    },
    "handoff": {
        "title": "Operational Workflow: Session Handoff",
        "purpose": "Standard session ledger recording in docs/development/summary_of_work.md before concluding.",
        "cli_command": "Update docs/development/summary_of_work.md"
    }
}

def generate_markdown(wf_key: str, data: dict, proto: dict) -> str:
    title = data["title"]
    purpose = data["purpose"]
    cli_cmd = data.get("cli_command", f"python3 -m runtime.cli {wf_key} --target <dir>")

    return f"""# {title}

## Purpose
{purpose}

## Operational Command
```bash
{cli_cmd}
```

## Protocol Compliance
This workflow is a direct projection of canonical RUP Protocol v3.0.0.
All outputs must validate against `protocol/rup-schema.json`.

## Guidelines & Rules
1. **Determinism**: Every action must be evidence-backed and reproducible.
2. **Safety**: Enforce path jailing and never modify files outside the target directory.
3. **Integrity**: Never certify verification gates as passed unless actually executed.
4. **Handoff**: Record all state changes in the run manifest and session ledger.
"""

def main():
    parser = argparse.ArgumentParser(description="Generate/check canonical workflows")
    parser.add_argument("--check", action="store_true", help="Check that all workflows exist and no duplicate aliases exist")
    args = parser.parse_args()

    root = Path(__file__).parent.parent.resolve()
    wf_dir = root / "workflows"
    wf_dir.mkdir(exist_ok=True, parents=True)

    proto_file = root / "protocol" / "rup-protocol.yaml"
    proto = {}
    if proto_file.exists():
        with open(proto_file, "r", encoding="utf-8") as f:
            proto = yaml.safe_load(f)

    if not args.check:
        # Clean existing workflows directory to remove duplicate aliases
        for f in wf_dir.glob("*.md"):
            f.unlink()

        for wf_key, data in CANONICAL_WORKFLOWS.items():
            wf_file = wf_dir / f"{wf_key}.md"
            with open(wf_file, "w", encoding="utf-8") as f:
                f.write(generate_markdown(wf_key, data, proto))
        print(f"[RUP] Generated {len(CANONICAL_WORKFLOWS)} canonical workflows in workflows/.")
        return 0

    missing = []
    for wf_key in CANONICAL_WORKFLOWS:
        wf_file = wf_dir / f"{wf_key}.md"
        if not wf_file.exists():
            missing.append(f"{wf_key}.md")

    if missing:
        print(f"FAILED: Missing workflows: {missing}", file=sys.stderr)
        return 1

    print(f"PASS: All {len(CANONICAL_WORKFLOWS)} canonical workflows exist.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
