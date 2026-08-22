#!/usr/bin/env python3
"""
Capability Lineage and Mapping Generator for Skill-RUP.
Verifies semantic implementation across Python runtime AST symbols,
workflows, schemas, and guardrails against canonical RUP Protocol v3.0.0.
"""
import sys
import json
import argparse
import subprocess  # nosec B404
from pathlib import Path

# Add repo root to sys.path
ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

from runtime.capability_map import (
    CANONICAL_CAPABILITIES,
    PORT_CLASSES,
    _verify_implementation,
    _determine_verification_level,
)
from runtime.source_authority import SOURCE_AUTHORITY


def _run_pytest_node(skill_root: Path, node_id: str) -> bool:
    """Run a single pytest node and return True if it passes."""
    try:
        # node_id comes from the controlled CANONICAL_CAPABILITIES list; shell=False
        # and the executable path are fixed, so untrusted command injection is not
        # possible here.
        proc = subprocess.run(  # nosec B603
            [sys.executable, "-m", "pytest", node_id, "-v", "-q"],
            cwd=str(skill_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        return proc.returncode == 0
    except Exception:
        return False


def determine_verification_level(
    files_exist: bool,
    symbols_verified: bool,
    runtime_smoke_tests: list,
    semantic_tests: list,
    skill_root: Path,
) -> str:
    """
    Determine the honest verification level for a capability.

    Levels:
      - unverified: implementation files missing.
      - present: files exist but required AST symbols are missing.
      - structurally_verified: symbols exist but no tests are listed.
      - runtime_smoke_verified: runtime smoke tests pass (no semantic tests).
      - behaviorally_verified: semantic tests pass.
      - canonical_parity_verified: never auto-claimed; reserved for manual override.
    """
    if not files_exist:
        return "unverified"
    if not symbols_verified:
        return "present"
    if semantic_tests:
        all_pass = all(_run_pytest_node(skill_root, node) for node in semantic_tests)
        if all_pass:
            return "behaviorally_verified"
        return "structurally_verified"
    if runtime_smoke_tests:
        all_pass = all(_run_pytest_node(skill_root, node) for node in runtime_smoke_tests)
        if all_pass:
            return "runtime_smoke_verified"
        return "structurally_verified"
    return "structurally_verified"


def build_lineage(skill_root: Path, run_tests: bool = True) -> tuple:
    """
    Build the capability lineage records and identify any failed capabilities.

    Returns (lineage_records, failed_capabilities).
    """
    lineage = []
    failed_capabilities = []

    for cap in CANONICAL_CAPABILITIES:
        cid = cap["id"]
        category = cap.get("category", "lifecycle")
        title = cap.get("name", cid)
        modules = cap.get("modules", [])
        req_symbols = cap.get("symbols", [])
        runtime_smoke_tests = cap.get("runtime_smoke_tests", [])
        semantic_tests = cap.get("semantic_tests", [])

        impl = _verify_implementation(skill_root, modules, req_symbols)
        impl_files = [_module_path(m) for m in modules]

        if run_tests:
            verification_level = determine_verification_level(
                impl["files_exist"],
                impl["symbols_verified"],
                runtime_smoke_tests,
                semantic_tests,
                skill_root,
            )
        else:
            verification_level = _determine_verification_level(
                impl["files_exist"],
                impl["symbols_verified"],
                runtime_smoke_tests,
                semantic_tests,
            )

        # The curated port class is authoritative; verification evidence can
        # never upgrade it (audit P1-1/P1-2). Only a missing implementation
        # (files/symbols) demotes a capability to "unmapped".
        declared_class = cap.get("port_status", "agent_native")
        if declared_class not in PORT_CLASSES:
            declared_class = "agent_native"
        if impl["files_exist"] and impl["symbols_verified"]:
            port_status = declared_class
        else:
            port_status = "unmapped"

        record = {
            "id": cid,
            "category": category,
            "title": title,
            "mandatory": True,
            "port_class": declared_class,
            "port_status": port_status,
            "verification_level": verification_level,
            "transfer_rationale": cap.get(
                "transfer_rationale",
                "Canonical behavior defined in protocol/rup-protocol.yaml; downstream implementation in the listed modules.",
            ),
            "implementation": impl_files,
            "required_symbols": req_symbols,
            "runtime_smoke_tests": runtime_smoke_tests,
            "semantic_tests": semantic_tests,
            "translation_type": "agent-native-deterministic",
            "canonical_source": {
                "repository": SOURCE_AUTHORITY["canonical_repo"],
                "version": SOURCE_AUTHORITY["canonical_version"],
                "commit": SOURCE_AUTHORITY["canonical_commit"],
            },
        }
        lineage.append(record)

        if port_status == "unmapped":
            failed_capabilities.append(record)

    return lineage, failed_capabilities


def _module_path(module_name: str) -> str:
    """Convert a Python module name to a filesystem path relative to the skill root."""
    return module_name.replace(".", "/") + ".py"


def write_artifacts(skill_root: Path, lineage: list, failed_capabilities: list) -> None:
    """Persist machine-readable lineage and human-readable capability mapping docs."""
    # Save machine-readable lineage
    prov_dir = skill_root / "provenance"
    prov_dir.mkdir(parents=True, exist_ok=True)
    with open(prov_dir / "capability-lineage.json", "w", encoding="utf-8") as f:
        json.dump(lineage, f, indent=2)

    # Save human-readable capability mapping doc
    docs_dir = skill_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    with open(docs_dir / "CAPABILITY_MAPPING.md", "w", encoding="utf-8") as f:
        f.write("# Skill-RUP Capability Mapping & Provenance\n\n")
        f.write(
            f"**Canonical Source**: `{SOURCE_AUTHORITY['canonical_repo']}` "
            f"(v{SOURCE_AUTHORITY['canonical_version']} @ `{SOURCE_AUTHORITY['canonical_commit'][:8]}`)\n\n"
        )
        by_class = {}
        for record in lineage:
            by_class[record["port_status"]] = by_class.get(record["port_status"], 0) + 1
        summary = " | ".join(
            f"**{label}**: {by_class.get(key, 0)}"
            for label, key in (
                ("Deterministic", "deterministic"),
                ("Partial", "partial"),
                ("Agent-native", "agent_native"),
                ("Not ported", "not_ported"),
                ("Parity verified", "parity_verified"),
                ("Unmapped", "unmapped"),
            )
        )
        f.write(f"**Total Capabilities**: {len(lineage)} | {summary}\n\n")
        f.write(
            "| Capability ID | Title | Status | Verification Level | Transfer Rationale |\n"
        )
        f.write(
            "|---------------|-------|--------|--------------------|--------------------|\n"
        )
        for record in lineage:
            f.write(
                f"| `{record['id']}` | {record['title']} | "
                f"{record['port_status'].upper()} | {record['verification_level']} | "
                f"{record['transfer_rationale']} |\n"
            )


def main():
    parser = argparse.ArgumentParser(description="Build and verify Skill-RUP capability lineage")
    parser.add_argument("--check", action="store_true", help="Fail if any capability is unverified")
    parser.add_argument(
        "--no-tests",
        action="store_true",
        help="Skip running pytest nodes (use structural verification only)",
    )
    args = parser.parse_args()

    lineage, failed_capabilities = build_lineage(ROOT, run_tests=not args.no_tests)
    write_artifacts(ROOT, lineage, failed_capabilities)

    by_class = {}
    by_level = {}
    for record in lineage:
        by_class[record["port_status"]] = by_class.get(record["port_status"], 0) + 1
        by_level[record["verification_level"]] = by_level.get(record["verification_level"], 0) + 1

    print(f"[RUP] Generated capability lineage for {len(lineage)} canonical capabilities.")
    print(f"[RUP] By port class: {by_class}")
    print(f"[RUP] By verification level: {by_level}")

    if args.check:
        if failed_capabilities:
            print(
                f"FAILED: {len(failed_capabilities)} capabilities have no implementation "
                "(missing files or required symbols):",
                file=sys.stderr,
            )
            for fc in failed_capabilities:
                print(
                    f"  - {fc['id']}: {fc['title']} "
                    f"(level: {fc['verification_level']}, "
                    f"files: {fc['implementation']}, symbols: {fc['required_symbols']})",
                    file=sys.stderr,
                )
            return 1
        print(
            "PASS: every canonical capability maps to a declared port class "
            "(deterministic/partial/agent_native/not_ported/parity_verified) with present implementation; "
            "NOT_PORTED capabilities are reported as NOT_PORTED, never as ported."
        )
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
