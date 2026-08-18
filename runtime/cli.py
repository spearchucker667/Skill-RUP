"""
CLI entry point for RUP deterministic runtime.
"""
import argparse
import sys
from pathlib import Path

from .paths import RupPaths
from .state import StateManager
from .artifact_builder import ArtifactBuilder
from .discovery import DiscoveryPhase
from .planning import PlanningPhase
from .execution import ExecutionPhase
from .verification import VerificationPhase
from .reporting import ReportingPhase

def run_discovery(target_dir: Path):
    paths = RupPaths(target_dir)
    state = StateManager(paths)
    builder = ArtifactBuilder(paths)
    print(f"Starting RUP Discovery on {target_dir.resolve()}...")
    phase = DiscoveryPhase(target_dir, state, builder)
    phase.execute()
    print("Discovery complete. Generated RUP_DISCOVERY.json and RUP_DISCOVERY.md.")

def run_plan(target_dir: Path):
    paths = RupPaths(target_dir)
    state = StateManager(paths)
    builder = ArtifactBuilder(paths)
    print(f"Starting RUP Planning on {target_dir.resolve()}...")
    phase = PlanningPhase(target_dir, state, builder)
    phase.execute()
    print("Planning complete. Generated RUP_PLAN.json and RUP_PLAN.md.")

def run_execute(target_dir: Path):
    paths = RupPaths(target_dir)
    state = StateManager(paths)
    builder = ArtifactBuilder(paths)
    print(f"Starting RUP Execution on {target_dir.resolve()}...")
    phase = ExecutionPhase(target_dir, state, builder)
    phase.execute()
    print("Execution complete. Generated RUP_EXECUTION.json and RUP_EXECUTION.md.")

def run_verify(target_dir: Path):
    paths = RupPaths(target_dir)
    state = StateManager(paths)
    builder = ArtifactBuilder(paths)
    print(f"Starting RUP Verification on {target_dir.resolve()}...")
    phase = VerificationPhase(target_dir, state, builder)
    phase.execute()
    print("Verification complete. Generated RUP_VERIFICATION.json and RUP_VERIFICATION.md.")

def run_report(target_dir: Path):
    paths = RupPaths(target_dir)
    state = StateManager(paths)
    builder = ArtifactBuilder(paths)
    print(f"Starting RUP Reporting on {target_dir.resolve()}...")
    phase = ReportingPhase(target_dir, state, builder)
    phase.execute()
    print("Reporting complete. Generated RUP_FINAL_REPORT.json and RUP_FINAL_REPORT.md.")

def main():
    parser = argparse.ArgumentParser(description="RUP Protocol Deterministic Runtime")
    parser.add_argument("phase", choices=["discovery", "plan", "execute", "verify", "report"], help="Phase to execute")
    parser.add_argument("--target", type=Path, default=Path("."), help="Target repository directory")
    
    args = parser.parse_args()
    
    try:
        if args.phase == "discovery":
            run_discovery(args.target)
        elif args.phase == "plan":
            run_plan(args.target)
        elif args.phase == "execute":
            run_execute(args.target)
        elif args.phase == "verify":
            run_verify(args.target)
        elif args.phase == "report":
            run_report(args.target)
        else:
            print(f"Phase '{args.phase}' is not fully implemented in the Python runtime yet.")
            return 1
    except Exception as e:
        print(f"Fatal error during {args.phase}: {e}", file=sys.stderr)
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
