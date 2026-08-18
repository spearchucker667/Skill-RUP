#!/usr/bin/env python3
import argparse
import sys

import argparse
import sys
import subprocess
from pathlib import Path

def run_forward_test(fixtures_dir: str) -> int:
    target = Path(fixtures_dir).resolve()
    print(f"Running forward tests on fixtures in {target}...")
    
    cli_dir = Path(__file__).parent.parent
    
    phases = ["discovery", "plan", "execute", "verify", "report"]
    
    for phase in phases:
        print(f"--- Running {phase.upper()} ---")
        cmd = [sys.executable, "-m", "runtime.cli", phase, "--target", str(target)]
        res = subprocess.run(cmd, cwd=cli_dir, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"FAILED in phase {phase}:")
            print(res.stderr)
            return 1
        import json
        if phase == "verify":
            verify_json = target / "RUP_VERIFICATION.json"
            if verify_json.exists():
                try:
                    data = json.loads(verify_json.read_text())
                    if data.get("verification_results", {}).get("overall_status") == "failed":
                        print(f"FAILED in phase {phase}: overall_status is failed in JSON")
                        return 1
                except Exception as e:
                    print(f"FAILED to parse {verify_json}: {e}")
                    return 1
                    
        print(res.stdout)
        
    print("Forward tests PASS: All phases executed successfully.")
    return 0

def main():
    parser = argparse.ArgumentParser(description="Run realistic RUP forward tests")
    parser.add_argument("--fixtures", required=True, help="Path to fixtures directory")
    args = parser.parse_args()
    sys.exit(run_forward_test(args.fixtures))

if __name__ == "__main__":
    main()
