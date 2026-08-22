"""
CLI entry point for RUP deterministic runtime.
"""
import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import RupPaths
from .state import StateManager
from .artifact_builder import ArtifactBuilder
from .discovery import DiscoveryPhase
from .planning import PlanningPhase
from .execution import ExecutionPhase
from .verification import VerificationPhase
from .reporting import ReportingPhase
from .rollback import apply_rollback_operations
from .security import scan_repository_for_threats
from .__init__ import __version__, __protocol_version__

def run_discovery(
    target_dir: Path,
    state_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
    state: Optional[StateManager] = None,
    resume: bool = False,
):
    if state is not None:
        paths = state.paths
    else:
        paths = RupPaths(target_dir, state_dir=state_dir)
        state = StateManager(paths, run_id=run_id, resume=resume)
    builder = ArtifactBuilder(paths, state=state)
    print(f"[RUP] Starting Discovery on {target_dir.resolve()} (Run ID: {state.run_id})...")
    phase = DiscoveryPhase(target_dir, state, builder)
    res = phase.execute()
    state.update_session_state("discovery")
    print(f"[RUP] Discovery complete. Production readiness: {res.get('risk_assessment', {}).get('production_readiness_score')}/100.")
    return res

def run_plan(
    target_dir: Path,
    state_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
    time_budget: int = 45,
    max_files: int = 20,
    risk_tolerance: str = "medium",
    state: Optional[StateManager] = None,
    resume: bool = False,
):
    if state is not None:
        paths = state.paths
    else:
        paths = RupPaths(target_dir, state_dir=state_dir)
        state = StateManager(paths, run_id=run_id, resume=resume)
    builder = ArtifactBuilder(paths, state=state)
    print(f"[RUP] Starting Planning (Budget: {time_budget}m, Tolerance: {risk_tolerance})...")
    phase = PlanningPhase(
        target_dir,
        state,
        builder,
        time_budget_minutes=time_budget,
        max_files=max_files,
        risk_tolerance=risk_tolerance
    )
    res = phase.execute()
    state.update_session_state("planning")
    print(f"[RUP] Planning complete. Selected {len(res.get('selected_items', []))} items for execution.")
    return res

def run_execute(
    target_dir: Path,
    state_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
    state: Optional[StateManager] = None,
    resume: bool = False,
    allow_exec: bool = False,
    sandbox: str = "required",
    override_escalation: bool = False,
    workspace: Optional[str] = None,
    changed_only: bool = False,
):
    if state is not None:
        paths = state.paths
    else:
        paths = RupPaths(target_dir, state_dir=state_dir)
        state = StateManager(paths, run_id=run_id, resume=resume)
    builder = ArtifactBuilder(paths, state=state)
    scope_note = f" (workspace={workspace or 'changed' if changed_only else workspace})" if (workspace or changed_only) else ""
    print(f"[RUP] Starting Execution{scope_note}...")
    phase = ExecutionPhase(
        target_dir,
        state,
        builder,
        allow_exec=allow_exec,
        sandbox=sandbox,
        override_escalation=override_escalation,
        workspace=workspace,
        changed_only=changed_only,
    )
    res = phase.execute()
    state.update_session_state("execution")
    print(f"[RUP] Execution complete. Applied {len(res.get('changes', []))} changes.")
    return res

def run_verify(
    target_dir: Path,
    state_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
    strict: bool = False,
    risk_tolerance: str = "medium",
    state: Optional[StateManager] = None,
    resume: bool = False,
    allow_exec: bool = False,
    sandbox: str = "required",
    workspace: Optional[str] = None,
    changed_only: bool = False,
) -> bool:
    if state is not None:
        paths = state.paths
    else:
        paths = RupPaths(target_dir, state_dir=state_dir)
        state = StateManager(paths, run_id=run_id, resume=resume)
    builder = ArtifactBuilder(paths, state=state)
    effective_strict = strict or risk_tolerance == "low"
    print(f"[RUP] Starting Multi-Gate Verification (strict={effective_strict})...")
    phase = VerificationPhase(
        target_dir,
        state,
        builder,
        strict=effective_strict,
        allow_exec=allow_exec,
        sandbox=sandbox,
        workspace=workspace,
        changed_only=changed_only,
    )
    out = phase.execute()
    state.update_session_state("verification")
    status = out["verification_results"]["overall_status"]
    print(f"[RUP] Verification complete. Status: {status.upper()}.")
    if effective_strict:
        return status == "passed"
    return status in ("passed", "passed_with_warnings")

def run_rollback(
    target_dir: Path,
    state_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
    resume: bool = False,
    dry_run: bool = False,
) -> int:
    """Apply the structured rollback operations recorded by the execution phase.

    Consumes the single platform-neutral representation from execution-state.json
    (falling back to RUP_EXECUTION.json) — the same representation the final
    report and the rollback workflow use (audit P1-28).
    """
    paths = RupPaths(target_dir, state_dir=state_dir)
    state = StateManager(paths, run_id=run_id, resume=resume)

    operations: Optional[List[Dict[str, Any]]] = None
    exec_state = state.load_json("execution-state.json")
    if isinstance(exec_state, dict) and exec_state.get("rollback_operations"):
        operations = exec_state["rollback_operations"]
    else:
        exec_data = state.load_json("RUP_EXECUTION.json")
        if isinstance(exec_data, dict):
            operations = exec_data.get("rollback_procedure", {}).get("operations")

    if not operations:
        print("[RUP] No rollback operations recorded; nothing to roll back.")
        return 0

    print(f"[RUP] Applying {len(operations)} rollback operation(s) (dry_run={dry_run})...")
    result = apply_rollback_operations(
        target_dir, operations, state_dir=paths.state_dir, dry_run=dry_run
    )
    for res in result["results"]:
        print(f"  [{res['status']}] {res.get('op')}: {res.get('path', '')}")
        if res.get("reason"):
            print(f"      reason: {res['reason']}")
    print(
        f"[RUP] Rollback complete: {result['applied']} applied, {result['failed']} failed."
    )
    return 0 if result["failed"] == 0 else 1


def run_migrate(target_dir: Path, state_dir: Optional[Path] = None, run_id: Optional[str] = None) -> Dict[str, Any]:
    paths = RupPaths(target_dir, state_dir=state_dir)
    state = StateManager(paths, run_id=run_id)
    print(f"[RUP] Migrating legacy root-level state into {paths.state_dir}...")
    result = state.migrate_legacy_state()
    print(f"[RUP] Migration complete. {result['count']} artifact(s) imported with provenance.")
    return result


def run_report(
    target_dir: Path,
    state_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
    state: Optional[StateManager] = None,
    resume: bool = False,
):
    if state is not None:
        paths = state.paths
    else:
        paths = RupPaths(target_dir, state_dir=state_dir)
        state = StateManager(paths, run_id=run_id, resume=resume)
    builder = ArtifactBuilder(paths, state=state)
    print(f"[RUP] Generating Final Report...")
    phase = ReportingPhase(target_dir, state, builder)
    res = phase.execute()
    state.update_session_state("completed")

    # Generate final run manifest
    plan_data = state.load_json("RUP_PLAN.json")
    exec_data = state.load_json("RUP_EXECUTION.json")
    ver_data = state.load_json("RUP_VERIFICATION.json")
    state.generate_and_save_manifest(
        phases_completed=["discovery", "plan", "execution", "verification", "reporting"],
        selected_items=plan_data.get("selected_items", []),
        execution_changes_count=len(exec_data.get("changes", [])),
        verification_status=ver_data.get("verification_results", {}).get("overall_status", "unknown")
    )
    print("[RUP] Final Report and Run Manifest generated.")
    return res

def run_full_lifecycle(
    target_dir: Path,
    state_dir: Optional[Path] = None,
    time_budget: int = 45,
    max_files: int = 20,
    risk_tolerance: str = "medium",
    strict: bool = False,
    override_escalation: bool = False,
    allow_exec: bool = False,
    sandbox: str = "required",
    workspace: Optional[str] = None,
    changed_only: bool = False,
) -> int:
    """Execute complete 4-phase RUP lifecycle."""
    paths = RupPaths(target_dir, state_dir=state_dir)
    # A full lifecycle always starts fresh; it must never silently resume a
    # completed or partially-completed previous run.
    state = StateManager(paths, resume=False)

    run_discovery(target_dir, state=state)

    # RUP-SEC-002: the adversarial trust gate runs immediately after discovery
    # and before any phase that could execute target-controlled commands. A
    # hostile repository cannot trigger test/build execution without
    # --allow-exec.
    threat_findings = scan_repository_for_threats(target_dir)
    if threat_findings and not allow_exec:
        print(
            f"[RUP] Refusing to continue: {len(threat_findings)} adversarial instruction "
            "pattern(s) detected in target content (e.g. "
            f"{threat_findings[0].get('file')}). Pass --allow-exec to explicitly "
            "opt into executing target-controlled commands.",
            file=sys.stderr,
        )
        return 1

    plan_data = run_plan(
        target_dir,
        time_budget=time_budget,
        max_files=max_files,
        risk_tolerance=risk_tolerance,
        state=state,
    )

    plan_state = state.load_json("plan-state.json")
    if plan_state.get("requires_explicit_override") and not override_escalation:
        print(
            "[RUP] Planning produced escalations that require explicit override. "
            "Use --override-escalation to continue.",
            file=sys.stderr,
        )
        return 1

    run_execute(
        target_dir,
        state=state,
        allow_exec=allow_exec,
        sandbox=sandbox,
        override_escalation=override_escalation,
        workspace=workspace,
        changed_only=changed_only,
    )
    passed = run_verify(
        target_dir,
        strict=strict,
        risk_tolerance=risk_tolerance,
        state=state,
        allow_exec=allow_exec,
        sandbox=sandbox,
        workspace=workspace,
        changed_only=changed_only,
    )
    report = run_report(target_dir, state=state)

    ready = report.get("summary", {}).get("ready_for_submission", False)
    return 0 if (passed and ready) else 1

def main():
    parser = argparse.ArgumentParser(description=f"Skill-RUP CLI (Runtime v{__version__}, Protocol v{__protocol_version__})")
    parser.add_argument("phase", choices=["discovery", "plan", "execute", "verify", "report", "run", "rollback", "migrate", "all"], help="Phase or full lifecycle to execute")
    parser.add_argument("--target", type=Path, default=Path("."), help="Target repository directory")
    parser.add_argument("--state-dir", type=Path, default=None, help="Directory to store state and artifacts (default: <target>/.rup)")
    parser.add_argument("--time-budget", type=int, default=45, help="Time budget in minutes for planning")
    parser.add_argument("--max-files", type=int, default=20, help="Max files to modify per run")
    parser.add_argument("--risk-tolerance", choices=["low", "medium", "high"], default="medium", help="Risk tolerance for planning")
    parser.add_argument("--strict", action="store_true", help="Fail verification on warnings or skipped gates")
    parser.add_argument("--resume", action="store_true", help="Resume an existing session (phase-only commands)")
    parser.add_argument("--override-escalation", action="store_true", help="Continue a full lifecycle even when P0 items are escalated")
    parser.add_argument(
        "--allow-exec",
        action="store_true",
        help="Explicitly allow executing target-controlled commands even when adversarial content is detected",
    )
    parser.add_argument(
        "--sandbox",
        choices=["required", "preferred", "off"],
        default="required",
        help="Sandbox policy for target-controlled commands (default: required; refuse when no sandbox is detected)",
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="Monorepo: restrict execution/verification to this workspace package (per-package tooling)",
    )
    parser.add_argument(
        "--changed-packages",
        action="store_true",
        help="Monorepo: restrict execution to packages containing git changes vs HEAD",
    )
    parser.add_argument("--version", action="version", version=f"Skill-RUP v{__version__} (Protocol v{__protocol_version__})")

    args = parser.parse_args()

    # Ensure the target directory is absolute before passing it to phase runners.
    # Phase modules invoke subprocesses with cwd=self.target_dir, which must be
    # an absolute path to satisfy the secure command runner.
    args.target = args.target.resolve()

    try:
        if args.phase in ("run", "all"):
            return run_full_lifecycle(
                args.target,
                state_dir=args.state_dir,
                time_budget=args.time_budget,
                max_files=args.max_files,
                risk_tolerance=args.risk_tolerance,
                strict=args.strict,
                override_escalation=args.override_escalation,
                allow_exec=args.allow_exec,
                sandbox=args.sandbox,
                workspace=args.workspace,
                changed_only=args.changed_packages,
            )
        elif args.phase == "discovery":
            run_discovery(args.target, state_dir=args.state_dir, resume=args.resume)
        elif args.phase == "plan":
            run_plan(
                args.target,
                state_dir=args.state_dir,
                time_budget=args.time_budget,
                max_files=args.max_files,
                risk_tolerance=args.risk_tolerance,
                resume=args.resume,
            )
        elif args.phase == "execute":
            run_execute(
                args.target,
                state_dir=args.state_dir,
                resume=args.resume,
                allow_exec=args.allow_exec,
                sandbox=args.sandbox,
                override_escalation=args.override_escalation,
                workspace=args.workspace,
                changed_only=args.changed_packages,
            )
        elif args.phase == "verify":
            if not run_verify(
                args.target,
                state_dir=args.state_dir,
                strict=args.strict,
                risk_tolerance=args.risk_tolerance,
                resume=args.resume,
                allow_exec=args.allow_exec,
                sandbox=args.sandbox,
                workspace=args.workspace,
                changed_only=args.changed_packages,
            ):
                print("[RUP] Verification failed.", file=sys.stderr)
                return 1
        elif args.phase == "report":
            run_report(args.target, state_dir=args.state_dir, resume=args.resume)
        elif args.phase == "rollback":
            return run_rollback(
                args.target,
                state_dir=args.state_dir,
                resume=args.resume,
            )
        elif args.phase == "migrate":
            run_migrate(args.target, state_dir=args.state_dir)
    except Exception as e:
        print(f"[RUP] Fatal error during {args.phase}: {e}", file=sys.stderr)
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())

