#!/usr/bin/env python3
"""
Generate and validate canonical, deterministic agent workflow files for Skill-RUP.

Workflows are derived from protocol/rup-protocol.yaml (phases and workstreams)
and a small set of operational workflows preserved for compatibility. The
generator never deletes existing files; it only writes files whose expected
content differs from what is on disk.
"""
import sys
import argparse
import yaml
from pathlib import Path

# Add repo root to sys.path so we can import runtime helpers.
ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

from runtime.security import safe_load_yaml


# Operational workflows are not part of the canonical protocol but are kept for
# compatibility with the existing workflow tree.
OPERATIONAL_WORKFLOWS = {
    "quick-run": {
        "title": "Operational Workflow: Quick Run",
        "purpose": "Rapid automated triage and critical P0 gap remediation within a constrained 15-minute time budget.",
        "cli_command": "python3 -m runtime.cli run --target <dir> --time-budget 15",
    },
    "hotfix": {
        "title": "Operational Workflow: Hotfix",
        "purpose": "Isolated, surgical fix for production regressions with minimal change footprint.",
        "cli_command": "python3 -m runtime.cli run --target <dir> --max-files 3 --risk-tolerance low",
    },
    "monorepo": {
        "title": "Operational Workflow: Monorepo Orchestration",
        "purpose": "Scoped execution across workspace packages (pnpm, nx, turborepo, cargo workspaces, go work).",
        "cli_command": "python3 -m runtime.cli run --target <dir>",
    },
    "rollback": {
        "title": "Operational Workflow: Rollback & Reversion",
        "purpose": "Deterministic reversion of executed changes using baseline git checkpoints and cleanup commands.",
        "cli_command": "git checkout -- <modified_files> && rm -f <created_files>",
    },
    "handoff": {
        "title": "Operational Workflow: Session Handoff",
        "purpose": "Standard session ledger recording in docs/development/summary_of_work.md before concluding.",
        "cli_command": "Update docs/development/summary_of_work.md",
    },
    "reporting": {
        "title": "Operational Workflow: Reporting",
        "purpose": "Evidence-backed final report generation, run manifest creation, follow-up tracking, and truthful publication instructions.",
        "cli_command": "python3 -m runtime.cli report --target <dir>",
    },
}


# Explicit filename mappings so generated names match the existing convention.
PHASE_FILENAME_ORDER = {
    "phase_1_discovery": "1-discovery",
    "phase_2_planning": "2-planning",
    "phase_3_execution": "3-execution",
    "phase_4_verification": "4-verification",
}

WORKSTREAM_FILENAME_MAP = {
    "bug_fixes": "bug-fixes",
    "tests": "tests",
    "ci_cd": "ci-cd",
    "documentation": "docs",
    "governance": "governance",
    "security": "security",
    "containerization": "containers",
    "observability": "observability",
}


def _yaml_dump(data: dict) -> str:
    """Deterministic YAML dump with a stable style."""
    return yaml.safe_dump(
        data,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=120,
    )


def _render_phase_rules(phase: dict) -> str:
    """Render phase steps as a numbered markdown list."""
    lines = []
    for step in phase.get("steps", []):
        name = step.get("name", "")
        actions = step.get("actions", [])
        action_text = " ".join(actions) if actions else ""
        lines.append(f"1. **{name}**: {action_text}")
    return "\n".join(lines) if lines else "Follow canonical RUP directives for this workflow."


def _render_workstream_rules(workstream: dict) -> str:
    """Render workstream process as a bulleted markdown list."""
    process = workstream.get("process", [])
    if process:
        lines = []
        for item in process:
            step = item.get("step", "")
            details = item.get("details", "")
            lines.append(f"- **{step}**: {details}")
        return "\n".join(lines)
    return "Follow canonical RUP directives for this workflow."


def _title_case(name: str) -> str:
    """Convert a snake_case or hyphenated name to a title-case string."""
    return " ".join(part.capitalize() for part in name.replace("-", "_").split("_"))


def generate_phase_markdown(phase: dict, number: int) -> str:
    """Generate deterministic markdown for a canonical protocol phase."""
    name = phase.get("name", "")
    title = f"{number} {_title_case(name)} Workflow"
    purpose = name or "No description provided."
    rules = _render_phase_rules(phase)
    raw_data = _yaml_dump({k: v for k, v in phase.items() if k != "output_template"})

    return f"""# {title}

## Purpose
{purpose}

## Canonical Rules & Process
{rules}

## Raw Protocol Data
```yaml
{raw_data}```

## Validation
Must comply with `rup-schema.json`.
"""


def generate_workstream_markdown(ws_key: str, workstream: dict) -> str:
    """Generate deterministic markdown for a canonical protocol workstream."""
    name = _title_case(ws_key)
    title = f"{name} Workflow"
    purpose = workstream.get("description", "No description provided.")
    rules = _render_workstream_rules(workstream)
    raw_data = _yaml_dump(workstream)

    return f"""# {title}

## Purpose
{purpose}

## Canonical Rules & Process
{rules}

## Raw Protocol Data
```yaml
{raw_data}```

## Validation
Must comply with `rup-schema.json`.
"""


def generate_operational_markdown(wf_key: str, data: dict) -> str:
    """Generate deterministic markdown for an operational workflow."""
    title = data["title"]
    purpose = data["purpose"]
    cli_cmd = data.get("cli_command", "")
    raw_data = _yaml_dump({"description": purpose, "cli_command": cli_cmd})

    return f"""# {title}

## Purpose
{purpose}

## Operational Command
```bash
{cli_cmd}
```

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
{raw_data}```

## Validation
Must comply with `rup-schema.json`.
"""


def load_canonical_workflows(proto_path: Path) -> dict:
    """Load phases and workstreams from the canonical protocol YAML."""
    proto = safe_load_yaml(proto_path)
    workflows = {}

    for phase in proto.get("phases", []):
        phase_id = phase.get("id", "")
        if phase_id in PHASE_FILENAME_ORDER:
            filename = PHASE_FILENAME_ORDER[phase_id]
            workflows[filename] = ("phase", phase)

        for ws_key, workstream in phase.get("workstreams", {}).items():
            if ws_key in WORKSTREAM_FILENAME_MAP:
                filename = WORKSTREAM_FILENAME_MAP[ws_key]
                workflows[filename] = ("workstream", ws_key, workstream)

    return workflows


def expected_workflow_content(wf_type: str, *args) -> str:
    """Return the deterministic markdown content for a workflow entry."""
    if wf_type == "phase":
        phase, = args
        number = list(PHASE_FILENAME_ORDER.keys()).index(phase["id"]) + 1
        return generate_phase_markdown(phase, number)
    if wf_type == "workstream":
        ws_key, workstream = args
        return generate_workstream_markdown(ws_key, workstream)
    if wf_type == "operational":
        wf_key, data = args
        return generate_operational_markdown(wf_key, data)
    raise ValueError(f"Unknown workflow type: {wf_type}")


def main():
    parser = argparse.ArgumentParser(description="Generate/check canonical workflows")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check that canonical workflows exist with deterministic content",
    )
    args = parser.parse_args()

    root = Path(__file__).parent.parent.resolve()
    wf_dir = root / "workflows"
    wf_dir.mkdir(exist_ok=True, parents=True)

    proto_file = root / "protocol" / "rup-protocol.yaml"
    canonical = load_canonical_workflows(proto_file)

    missing = []
    mismatched = []
    written = []

    for filename, payload in canonical.items():
        wf_type = payload[0]
        content = expected_workflow_content(wf_type, *payload[1:])
        wf_file = wf_dir / f"{filename}.md"

        if not wf_file.exists():
            missing.append(filename)
            if not args.check:
                wf_file.write_text(content, encoding="utf-8")
                written.append(filename)
            continue

        existing = wf_file.read_text(encoding="utf-8")
        if existing != content:
            mismatched.append(filename)
            if not args.check:
                wf_file.write_text(content, encoding="utf-8")
                written.append(filename)

    # Report in check mode.
    if args.check:
        if missing or mismatched:
            if missing:
                print(f"FAILED: Missing workflows: {missing}", file=sys.stderr)
            if mismatched:
                print(
                    f"FAILED: Workflows with non-deterministic/mismatched content: {mismatched}",
                    file=sys.stderr,
                )
            return 1
        print(f"PASS: All {len(canonical)} canonical workflows exist with deterministic content.")
        return 0

    # Generate mode.
    print(f"[RUP] Canonical workflows checked: {len(canonical)}.")
    if written:
        print(f"[RUP] Wrote/updated {len(written)} workflow file(s): {written}")
    else:
        print("[RUP] All canonical workflow files already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
