#!/usr/bin/env python3
"""
generate_runtime.py - Non-destructive runtime scaffold validator and initializer.
Safely checks or creates missing module files without overwriting existing code.
"""
import argparse
import sys
from pathlib import Path

REQUIRED_MODULES = [
    "__init__", "cli", "paths", "models", "state", "inventory",
    "discovery", "planning", "execution", "verification", "reporting",
    "artifact_builder", "capability_map", "provenance", "source_authority",
    "command_runner", "tool_detection", "security", "redaction", "platform"
]

MODULE_TEMPLATE = '''"""
{name} module for RUP deterministic runtime.
"""
from pathlib import Path
'''

def main() -> int:
    parser = argparse.ArgumentParser(description="Validate or initialize RUP runtime modules safely.")
    parser.add_argument("--check", action="store_true", help="Check that all runtime modules exist without modifying files")
    args = parser.parse_args()

    root = Path(__file__).parent.parent.resolve()
    rt_dir = root / "runtime"
    rt_dir.mkdir(exist_ok=True, parents=True)

    missing = []
    created = []
    existing = []

    for mod in REQUIRED_MODULES:
        mod_path = rt_dir / f"{mod}.py"
        if not mod_path.exists():
            missing.append(mod)
            if not args.check:
                with open(mod_path, "w", encoding="utf-8") as f:
                    f.write(MODULE_TEMPLATE.format(name=mod))
                created.append(mod)
        else:
            existing.append(mod)

    if args.check:
        if missing:
            print(f"Error: Missing runtime modules: {missing}", file=sys.stderr)
            return 1
        print(f"All {len(REQUIRED_MODULES)} runtime modules exist.")
        return 0

    print(f"Runtime modules status: {len(existing)} existing, {len(created)} created.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
