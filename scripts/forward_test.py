#!/usr/bin/env python3
"""
RUP forward-test runner.

Builds disposable fixture repositories, runs the full RUP lifecycle, and
validates that all expected .rup/ artifacts are produced, schema-valid, and
internally consistent.
"""
import argparse
import json
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

# The tests package must be importable from the repository root.
REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

from tests.forward.fixtures import BUILDERS, build_fixture  # noqa: E402

EXPECTED_ARTIFACTS = [
    "RUP_DISCOVERY.json",
    "RUP_PLAN.json",
    "RUP_EXECUTION.json",
    "RUP_VERIFICATION.json",
    "run-manifest.json",
    "RUP_DISCOVERY.md",
    "RUP_PLAN.md",
    "RUP_EXECUTION.md",
    "RUP_VERIFICATION.md",
    "RUP_FINAL_REPORT.md",
    "RUP_FINAL_REPORT.json",
    "session-state.json",
]

REQUIRED_PHASE_ORDER = ["discovery", "planning", "execution", "verification", "completed"]

# Fixtures where the RUP lifecycle is expected to end with a non-zero exit
# because verification correctly reports failed/problematic state.
EXPECTED_TO_FAIL_LIFECYCLE = {"failing_tests", "security_findings"}
# Fixtures where malicious root-level state must be ignored. The lifecycle is
# allowed to succeed as long as the malicious plan was not executed.
ADVERSARIAL_STATE_FIXTURES = {"adversarial_state"}


def _run(cmd: List[str], cwd: Path, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def validate_json_artifact(artifact_path: Path, output_type: str) -> Tuple[bool, str]:
    schema_path = REPO_ROOT / "protocol" / "rup-schema.json"
    result = subprocess.run(  # nosec B603
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "validate_rup.py"),
            "--schema",
            str(schema_path),
            "output",
            str(artifact_path),
            output_type,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, result.stdout + result.stderr
    return True, ""


def check_artifacts(target_dir: Path) -> List[str]:
    errors = []
    state_dir = target_dir / ".rup"
    for name in EXPECTED_ARTIFACTS:
        path = state_dir / name
        if not path.exists():
            errors.append(f"Missing expected artifact: {path.relative_to(target_dir)}")
            continue
        if name.endswith(".json") and name not in ("run-manifest.json", "session-state.json"):
            output_type = name.replace("RUP_", "").replace(".json", "").lower()
            if output_type in ("discovery", "plan", "execution", "verification"):
                ok, msg = validate_json_artifact(path, output_type)
                if not ok:
                    errors.append(f"Schema validation failed for {name}: {msg}")
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                errors.append(f"Malformed JSON in {name}: {e}")
    return errors


def check_run_identity(target_dir: Path) -> List[str]:
    errors = []
    state_dir = target_dir / ".rup"

    session_path = state_dir / "session-state.json"
    manifest_path = state_dir / "run-manifest.json"

    session = json.loads(session_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if session.get("run_id") != manifest.get("run_id"):
        errors.append(
            f"Run ID mismatch: session={session.get('run_id')} manifest={manifest.get('run_id')}"
        )

    phases = session.get("artifacts_generated", [])
    manifest_phases = manifest.get("phases_completed", [])
    for phase in ("RUP_DISCOVERY.json", "RUP_PLAN.json", "RUP_EXECUTION.json", "RUP_VERIFICATION.json"):
        if phase not in phases:
            errors.append(f"Session state missing artifact: {phase}")

    expected_manifest_phases = ["discovery", "plan", "execution", "verification", "reporting"]
    for phase in expected_manifest_phases:
        if phase not in manifest_phases:
            errors.append(f"Run manifest missing phase: {phase}")

    return errors


def check_fixture_specific(target_dir: Path, fixture_name: str) -> List[str]:
    errors = []
    state_dir = target_dir / ".rup"

    if fixture_name == "failing_tests":
        data = json.loads((state_dir / "RUP_VERIFICATION.json").read_text(encoding="utf-8"))
        status = data.get("verification_results", {}).get("overall_status")
        if status != "failed":
            errors.append(f"failing_tests fixture expected verification failed, got {status}")

    if fixture_name == "dirty_git":
        data = json.loads((state_dir / "RUP_EXECUTION.json").read_text(encoding="utf-8"))
        changes = [c.get("file_path") for c in data.get("changes", [])]
        if "src/existing.py" in changes:
            errors.append("Pre-existing dirty tracked file was attributed to RUP changes")
        if "untracked.txt" in changes:
            errors.append("Pre-existing untracked file was attributed to RUP changes")

    if fixture_name == "adversarial_state":
        # With root-state fallback removed, the malicious root files must be ignored.
        # If a legitimate lifecycle completed, ensure the malicious plan was not used.
        if (state_dir / "run-manifest.json").exists():
            exec_data = json.loads((state_dir / "RUP_EXECUTION.json").read_text(encoding="utf-8"))
            changes = [c.get("file_path") for c in exec_data.get("changes", [])]
            if "/etc/passwd" in changes:
                errors.append("Adversarial root state was trusted and acted upon")

            plan_data = json.loads((state_dir / "RUP_PLAN.json").read_text(encoding="utf-8"))
            selected = set(plan_data.get("selected_items", []))
            if "EVIL-001" in selected:
                errors.append("Adversarial root-level RUP_PLAN.json was trusted")

    if fixture_name == "symlink_escape":
        # The runtime must not escape the target directory via symlinks.
        data = json.loads((state_dir / "RUP_DISCOVERY.json").read_text(encoding="utf-8"))
        files = data.get("repo_metadata", {}).get("file_count", 0)
        if files > 10:
            errors.append(f"Symlink escape may have been followed ({files} files discovered)")

    return errors


def run_fixture(fixture_name: str, fixtures_base: Path) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    target_dir = Path(tempfile.mkdtemp(prefix=f"rup_fwd_{fixture_name}_", dir=str(fixtures_base)))

    try:
        build_fixture(fixture_name, target_dir)

        cmd = [sys.executable, "-m", "runtime.cli", "all", "--target", str(target_dir)]
        result = _run(cmd, REPO_ROOT)

        expected_fail = fixture_name in EXPECTED_TO_FAIL_LIFECYCLE
        is_adversarial = fixture_name in ADVERSARIAL_STATE_FIXTURES

        if is_adversarial:
            # The malicious root files must be ignored. The lifecycle may either
            # fail cleanly or generate a legitimate plan; either outcome is OK as
            # long as the adversarial changes are not attributed to RUP.
            if (target_dir / ".rup" / "RUP_EXECUTION.json").exists():
                errors.extend(check_artifacts(target_dir))
                if not errors:
                    errors.extend(check_run_identity(target_dir))
                errors.extend(check_fixture_specific(target_dir, fixture_name))
            return (not errors), errors

        if result.returncode != 0 and not expected_fail:
            errors.append(f"Lifecycle exited {result.returncode}: {result.stderr}")
            return False, errors

        if result.returncode == 0 and expected_fail:
            errors.append(f"Lifecycle unexpectedly succeeded for {fixture_name}")
            return False, errors

        errors.extend(check_artifacts(target_dir))
        if not errors:
            errors.extend(check_run_identity(target_dir))
            errors.extend(check_fixture_specific(target_dir, fixture_name))

        return (not errors), errors
    finally:
        shutil.rmtree(target_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RUP forward tests on disposable fixtures")
    parser.add_argument(
        "--fixtures",
        default=str(REPO_ROOT / "tests" / "fixtures"),
        help="Directory used as the parent for temporary fixture workspaces",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        help="Run only the named fixture (may be given multiple times)",
    )
    args = parser.parse_args()

    fixtures_base = Path(args.fixtures)
    fixtures_base.mkdir(parents=True, exist_ok=True)

    fixture_names = args.only if args.only else list(BUILDERS.keys())
    failed = []
    passed = []

    for name in fixture_names:
        print(f"--- Forward test fixture: {name} ---")
        ok, errors = run_fixture(name, fixtures_base)
        if ok:
            print(f"PASS: {name}")
            passed.append(name)
        else:
            print(f"FAIL: {name}")
            for err in errors:
                print(f"  - {err}")
            failed.append(name)

    print("=" * 50)
    print(f"Passed: {len(passed)}/{len(fixture_names)}")
    print(f"Failed: {len(failed)}/{len(fixture_names)}")
    if failed:
        print(f"Failed fixtures: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("All forward tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
