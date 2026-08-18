"""
CLI entry point for RUP deterministic runtime.
"""
import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .paths import RupPaths
from .state import StateManager
from .artifact_builder import ArtifactBuilder
from .discovery import DiscoveryPhase
from .planning import PlanningPhase
from .execution import ExecutionPhase
from .verification import VerificationPhase
from .reporting import ReportingPhase
from .__init__ import __version__, __protocol_version__

def run_discovery(target_dir: Path, state_dir: Optional[Path] = None, run_id: Optional[str] = None):
    paths = RupPaths(target_dir, state_dir=state_dir)
    state = StateManager(paths, run_id=run_id)
    builder = ArtifactBuilder(paths)
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
    risk_tolerance: str = "medium"
):
    paths = RupPaths(target_dir, state_dir=state_dir)
    state = StateManager(paths, run_id=run_id)
    builder = ArtifactBuilder(paths)
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

def run_execute(target_dir: Path, state_dir: Optional[Path] = None, run_id: Optional[str] = None):
    paths = RupPaths(target_dir, state_dir=state_dir)
    state = StateManager(paths, run_id=run_id)
    builder = ArtifactBuilder(paths)
    print(f"[RUP] Starting Execution...")
    phase = ExecutionPhase(target_dir, state, builder)
    res = phase.execute()
    state.update_session_state("execution")
    print(f"[RUP] Execution complete. Applied {len(res.get('changes', []))} changes.")
    return res

def run_verify(target_dir: Path, state_dir: Optional[Path] = None, run_id: Optional[str] = None, strict: bool = False) -> bool:
    paths = RupPaths(target_dir, state_dir=state_dir)
    state = StateManager(paths, run_id=run_id)
    builder = ArtifactBuilder(paths)
    print(f"[RUP] Starting Multi-Gate Verification...")
    phase = VerificationPhase(target_dir, state, builder, strict=strict)
    out = phase.execute()
    state.update_session_state("verification")
    status = out["verification_results"]["overall_status"]
    print(f"[RUP] Verification complete. Status: {status.upper()}.")
    if strict:
        return status == "passed"
    return status in ("passed", "passed_with_warnings")

def run_migrate(target_dir: Path, state_dir: Optional[Path] = None, run_id: Optional[str] = None) -> Dict[str, Any]:
    paths = RupPaths(target_dir, state_dir=state_dir)
    state = StateManager(paths, run_id=run_id)
    print(f"[RUP] Migrating legacy root-level state into {paths.state_dir}...")
    result = state.migrate_legacy_state()
    print(f"[RUP] Migration complete. {result['count']} artifact(s) imported with provenance.")
    return result


def run_report(target_dir: Path, state_dir: Optional[Path] = None, run_id: Optional[str] = None):
    paths = RupPaths(target_dir, state_dir=state_dir)
    state = StateManager(paths, run_id=run_id)
    builder = ArtifactBuilder(paths)
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
    strict: bool = False
) -> int:
    """Execute complete 4-phase RUP lifecycle."""
    paths = RupPaths(target_dir, state_dir=state_dir)
    state = StateManager(paths)
    run_id = state.run_id

    run_discovery(target_dir, state_dir=state_dir, run_id=run_id)
    run_plan(target_dir, state_dir=state_dir, run_id=run_id, time_budget=time_budget, max_files=max_files, risk_tolerance=risk_tolerance)
    run_execute(target_dir, state_dir=state_dir, run_id=run_id)
    passed = run_verify(target_dir, state_dir=state_dir, run_id=run_id, strict=strict)
    run_report(target_dir, state_dir=state_dir, run_id=run_id)

    return 0 if passed else 1

def main():
    parser = argparse.ArgumentParser(description=f"Skill-RUP CLI (Runtime v{__version__}, Protocol v{__protocol_version__})")
    parser.add_argument("phase", choices=["discovery", "plan", "execute", "verify", "report", "run", "migrate", "all"], help="Phase or full lifecycle to execute")
    parser.add_argument("--target", type=Path, default=Path("."), help="Target repository directory")
    parser.add_argument("--state-dir", type=Path, default=None, help="Directory to store state and artifacts (default: <target>/.rup)")
    parser.add_argument("--time-budget", type=int, default=45, help="Time budget in minutes for planning")
    parser.add_argument("--max-files", type=int, default=20, help="Max files to modify per run")
    parser.add_argument("--risk-tolerance", choices=["low", "medium", "high"], default="medium", help="Risk tolerance for planning")
    parser.add_argument("--strict", action="store_true", help="Fail verification on warnings or skipped gates")
    parser.add_argument("--version", action="version", version=f"Skill-RUP v{__version__} (Protocol v{__protocol_version__})")

    args = parser.parse_args()

    try:
        if args.phase in ("run", "all"):
            return run_full_lifecycle(
                args.target,
                state_dir=args.state_dir,
                time_budget=args.time_budget,
                max_files=args.max_files,
                risk_tolerance=args.risk_tolerance,
                strict=args.strict
            )
        elif args.phase == "discovery":
            run_discovery(args.target, state_dir=args.state_dir)
        elif args.phase == "plan":
            run_plan(
                args.target,
                state_dir=args.state_dir,
                time_budget=args.time_budget,
                max_files=args.max_files,
                risk_tolerance=args.risk_tolerance
            )
        elif args.phase == "execute":
            run_execute(args.target, state_dir=args.state_dir)
        elif args.phase == "verify":
            if not run_verify(args.target, state_dir=args.state_dir, strict=args.strict):
                print("[RUP] Verification failed.", file=sys.stderr)
                return 1
        elif args.phase == "report":
            run_report(args.target, state_dir=args.state_dir)
        elif args.phase == "migrate":
            run_migrate(args.target, state_dir=args.state_dir)
    except Exception as e:
        print(f"[RUP] Fatal error during {args.phase}: {e}", file=sys.stderr)
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())

