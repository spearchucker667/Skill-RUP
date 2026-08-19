#!/usr/bin/env python3
"""
RUP Protocol Validator v3.0.0

Validates RUP protocol YAML files and agent outputs against the JSON Schema.

Canonical usage:
    python validate_rup.py --schema protocol/rup-schema.json protocol <protocol.yaml>
    python validate_rup.py --schema protocol/rup-schema.json output <output.json> <discovery|plan|execution|verification>
    python validate_rup.py --schema protocol/rup-schema.json all <directory>

Backwards-compatible forms are also accepted.

Requirements:
    pip install jsonschema pyyaml

Author: Faye Håkansdotter
License: CC0-1.0
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
    from jsonschema import Draft202012Validator, ValidationError, SchemaError
except ImportError as e:
    print(f"Error: Missing required module: {e.name}")
    print("Install with: pip install jsonschema pyyaml")
    sys.exit(1)

def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except ValueError:
        return default


MAX_FILE_BYTES = _env_int("RUP_MAX_FILE_BYTES", 5 * 1024 * 1024)
MAX_YAML_ALIASES = _env_int("RUP_MAX_YAML_ALIASES", 50)


class LimitedAliasLoader(yaml.SafeLoader):
    """SafeLoader with alias expansion limits to prevent YAML bombs."""

    def __init__(self, stream):
        super().__init__(stream)
        self._alias_count = 0

    def compose_node(self, parent, index):  # type: ignore[override]
        if self.check_event(yaml.AliasEvent):
            self._alias_count += 1
            if self._alias_count > MAX_YAML_ALIASES:
                raise yaml.YAMLError(
                    f"YAML aliases exceed limit ({MAX_YAML_ALIASES})."
                )
        return super().compose_node(parent, index)


def _check_file_size(file_path: Path) -> None:
    size = file_path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(
            f"File too large: {file_path} ({size} bytes > {MAX_FILE_BYTES} bytes)"
        )


def _display_path(path: Path) -> str:
    """Return a display string for a path using forward slashes on all platforms."""
    return str(path).replace("\\", "/")


# ANSI color codes
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def colorize(text: str, color: str) -> str:
    """Add color to text if terminal supports it."""
    if sys.stdout.isatty():
        return f"{color}{text}{Colors.RESET}"
    return text


def _supports_unicode() -> bool:
    """Return True if stdout is configured for UTF-8; otherwise use ASCII fallbacks."""
    try:
        encoding = getattr(sys.stdout, "encoding", "") or ""
        return "utf" in encoding.lower()
    except Exception:
        return False


# Status symbols: Unicode when supported, ASCII fallbacks for constrained encodings.
CHECK = "✓" if _supports_unicode() else "OK"
CROSS = "✗" if _supports_unicode() else "FAIL"
WARN = "⚠" if _supports_unicode() else "WARN"


def _find_schema_path(schema_path: Optional[Path] = None) -> Path:
    """Resolve the RUP JSON Schema path on disk."""
    if schema_path is not None:
        p = Path(schema_path)
        if p.exists():
            return p.resolve()
        raise FileNotFoundError(f"Schema not found: {p}")

    # Check candidate paths in order of preference
    repo_root = Path(__file__).parent.parent.resolve()
    candidates = [
        repo_root / "protocol" / "rup-schema.json",
        repo_root / "rup-schema.json",
        Path.cwd() / "protocol" / "rup-schema.json",
        Path.cwd() / "rup-schema.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    raise FileNotFoundError(f"Schema not found. Searched: {[str(c) for c in candidates]}")


def load_schema(schema_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the RUP JSON Schema."""
    p = _find_schema_path(schema_path)
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)


def _resolve_derived_schema_path(schema_path: Optional[Path] = None) -> Optional[Path]:
    """Locate the Skill-RUP derived protocol schema extension.

    The canonical protocol schema lives at ``protocol/rup-schema.json`` and must
    remain a byte-for-byte copy of the upstream source. Downstream extensions
    (constraints, execution recommendations/rollback, prompt-injection scan,
    tool/reason metadata) live in ``schemas/rup-schema-derived.schema.json``.
    """
    if schema_path is None:
        return None
    repo_root = Path(schema_path).parent.parent.resolve()
    derived = repo_root / "schemas" / "rup-schema-derived.schema.json"
    if derived.is_file():
        return derived
    return None


def load_derived_schema(schema_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load the Skill-RUP derived protocol schema extension if it exists."""
    p = _resolve_derived_schema_path(schema_path)
    if p is None:
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_schemas_dir(schema_path: Optional[Path] = None) -> Optional[Path]:
    """Locate the derived-schemas directory relative to the canonical schema.

    The canonical layout places ``protocol/rup-schema.json`` at the repository
    root, with a sibling ``schemas/`` directory containing derived artifact
    schemas (run-manifest, session-state, final-report, rollback, handoff, etc.).
    """
    if schema_path is None:
        return None
    repo_root = Path(schema_path).parent.parent.resolve()
    schemas_dir = repo_root / "schemas"
    if schemas_dir.is_dir():
        return schemas_dir
    return None


def _load_derived_schemas(schemas_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Load all ``*.schema.json`` files from the derived schemas directory."""
    derived: Dict[str, Dict[str, Any]] = {}
    if not schemas_dir.is_dir():
        return derived
    for schema_file in schemas_dir.glob("*.schema.json"):
        try:
            _check_file_size(schema_file)
            with open(schema_file, "r", encoding="utf-8") as f:
                # Key by the artifact name, e.g. "run-manifest" for
                # "run-manifest.schema.json".
                key = schema_file.name[: -len(".schema.json")]
                derived[key] = json.load(f)
        except Exception as e:
            print(
                f"{colorize('Warning:', Colors.YELLOW)} Could not load derived schema {schema_file}: {e}"
            )
    return derived


def _validate_json_schema(schema_data: Dict[str, Any]) -> Tuple[bool, List[ValidationError]]:
    """Meta-validate a JSON Schema document against Draft 2020-12."""
    try:
        Draft202012Validator.check_schema(schema_data)
        return True, []
    except (ValidationError, SchemaError) as e:
        return False, [e]


def _validate_derived(
    instance_data: Dict[str, Any],
    schema_name: str,
    derived_schemas: Dict[str, Dict[str, Any]],
) -> Tuple[bool, List[ValidationError]]:
    """Validate an instance against a derived schema by name."""
    schema = derived_schemas.get(schema_name)
    if schema is None:
        raise ValueError(f"Derived schema not found: {schema_name}")
    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(instance_data))
    return len(errors) == 0, errors


def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load a YAML file."""
    _check_file_size(file_path)
    with open(file_path, 'r', encoding='utf-8') as f:
        # LimitedAliasLoader inherits from SafeLoader; arbitrary Python-object
        # construction is disabled and alias expansion is capped.
        return yaml.load(f, Loader=LimitedAliasLoader)  # nosec B506


def load_json(file_path: Path) -> Dict[str, Any]:
    """Load a JSON file."""
    _check_file_size(file_path)
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_validation_error(error: ValidationError, indent: int = 0) -> str:
    """Format a validation error for display."""
    prefix = "  " * indent
    # Path in the instance (file being validated)
    path = ".".join(str(p) for p in error.absolute_path) or "(root)"
    
    # Path in the schema that triggered the error
    schema_path = ".".join(str(p) for p in error.schema_path)
    
    lines = [
        f"{prefix}{colorize(CROSS, Colors.RED)} {colorize(path, Colors.CYAN)}",
        f"{prefix}  Message: {error.message}",
    ]
    
    if error.validator:
        lines.append(f"{prefix}  Validator: {error.validator} (at schema: {schema_path})")
    
    if error.validator_value and len(str(error.validator_value)) < 100:
        lines.append(f"{prefix}  Expected: {error.validator_value}")
    
    return "\n".join(lines)


def validate_protocol(
    protocol_data: Dict[str, Any],
    schema: Dict[str, Any]
) -> Tuple[bool, List[ValidationError]]:
    """Validate a protocol definition against the schema."""

    # Enforce schema version (derive expected version from the schema $id).
    # This keeps the validator behavior consistent when the schema is upgraded.
    expected_version: Optional[str] = None

    # Prefer an explicit schema self-version if present.
    schema_self_version = schema.get("x_rup_schema_version")
    if isinstance(schema_self_version, str):
        expected_version = schema_self_version
    else:
        schema_id = schema.get("$id")
        if isinstance(schema_id, str):
            import re
            m = re.search(r"/v(\d+\.\d+\.\d+)/", schema_id)
            if m:
                expected_version = m.group(1)

    format_checker = Draft202012Validator.FORMAT_CHECKER

    if expected_version and 'schema_version' in protocol_data:
        version = protocol_data['schema_version']
        if version != expected_version:
            error = ValidationError(
                f"Schema version mismatch. Expected {expected_version}, got {version}",
                validator="const",
                validator_value=expected_version,
                instance=version,
                schema_path=["properties", "schema_version"]
            )
            validator = Draft202012Validator(schema, format_checker=format_checker)
            errors = list(validator.iter_errors(protocol_data))
            errors.insert(0, error)
            return False, errors

    validator = Draft202012Validator(schema, format_checker=format_checker)
    errors = list(validator.iter_errors(protocol_data))
    return len(errors) == 0, errors


def validate_agent_output(
    output_data: Dict[str, Any],
    output_type: str,
    schema: Dict[str, Any],
    derived_schema: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[ValidationError]]:
    """Validate an agent output against the appropriate sub-schema.

    When ``derived_schema`` is supplied, output definitions are resolved from
    the derived schema first. This lets Skill-RUP keep ``protocol/rup-schema.json``
    byte-for-byte canonical while validating downstream runtime extensions
    (constraints, recommendations/rollback, prompt-injection scan, tool/reason
    metadata) against ``schemas/rup-schema-derived.schema.json``.
    """
    # Map output types to schema definitions
    type_map = {
        'discovery': 'DiscoveryReport',
        'plan': 'PlanOutput',
        'execution': 'ExecutionOutput',
        'verification': 'VerificationOutput'
    }

    if output_type not in type_map:
        raise ValueError(f"Unknown output type: {output_type}. Valid types: {list(type_map.keys())}")

    def_name = type_map[output_type]

    # Prefer the derived schema for output definitions; fall back to canonical.
    effective_schema = derived_schema if derived_schema is not None else schema
    if '$defs' not in effective_schema or def_name not in effective_schema['$defs']:
        raise ValueError(f"Schema definition not found: {def_name}")

    # Create a wrapper schema that references the definition
    # This allows the validator to properly resolve $refs
    wrapper_schema = {
        "$ref": f"#/$defs/{def_name}",
        "$defs": effective_schema.get("$defs", {})
    }

    format_checker = Draft202012Validator.FORMAT_CHECKER
    validator = Draft202012Validator(wrapper_schema, format_checker=format_checker)

    errors = list(validator.iter_errors(output_data))
    return len(errors) == 0, errors


def print_result(
    file_path: Path,
    valid: bool,
    errors: List[ValidationError],
    verbose: bool = False
) -> None:
    """Print validation result."""
    display = _display_path(file_path)
    if valid:
        print(f"{colorize(CHECK, Colors.GREEN)} {colorize(display, Colors.BOLD)}: {colorize('Valid', Colors.GREEN)}")
    else:
        print(f"{colorize(CROSS, Colors.RED)} {colorize(display, Colors.BOLD)}: {colorize('Invalid', Colors.RED)}")
        print(f"  Found {len(errors)} error(s):")
        
        # Show first 10 errors by default, all if verbose
        display_errors = errors if verbose else errors[:10]
        for error in display_errors:
            print(format_validation_error(error, indent=1))
        
        if not verbose and len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors (use --verbose to see all)")


def cmd_validate_protocol(args: argparse.Namespace) -> int:
    """Validate a protocol YAML file."""
    try:
        schema = load_schema(args.schema)
        protocol = load_yaml(Path(args.file))
        
        valid, errors = validate_protocol(protocol, schema)
        print_result(Path(args.file), valid, errors, args.verbose)
        
        return 0 if valid else 1
    
    except FileNotFoundError as e:
        print(f"{colorize('Error:', Colors.RED)} {e}")
        return 1
    except yaml.YAMLError as e:
        print(f"{colorize('Error:', Colors.RED)} Invalid YAML: {e}")
        return 1
    except Exception as e:
        print(f"{colorize('Error:', Colors.RED)} {e}")
        return 1


def cmd_validate_output(args: argparse.Namespace) -> int:
    """Validate an agent output JSON file."""
    try:
        schema_path = _find_schema_path(args.schema)
        schema = load_schema(schema_path)
        derived_schema = load_derived_schema(schema_path)
        output = load_json(Path(args.file))

        valid, errors = validate_agent_output(output, args.type, schema, derived_schema)
        print_result(Path(args.file), valid, errors, args.verbose)

        return 0 if valid else 1

    except FileNotFoundError as e:
        print(f"{colorize('Error:', Colors.RED)} {e}")
        return 1
    except json.JSONDecodeError as e:
        print(f"{colorize('Error:', Colors.RED)} Invalid JSON: {e}")
        return 1
    except ValueError as e:
        print(f"{colorize('Error:', Colors.RED)} {e}")
        return 1
    except Exception as e:
        print(f"{colorize('Error:', Colors.RED)} {e}")
        return 1


def _derived_schema_name(fname_lower: str) -> Optional[str]:
    """Map a JSON artifact filename to its derived schema name, if known."""
    exact_map = {
        "run-manifest.json": "run-manifest",
        "session-state.json": "session-state",
        "rup_final_report.json": "final-report",
    }
    if fname_lower in exact_map:
        return exact_map[fname_lower]
    if "rollback" in fname_lower and fname_lower.endswith(".json"):
        return "rollback"
    if "handoff" in fname_lower and fname_lower.endswith(".json"):
        return "handoff"
    return None


def cmd_validate_all(args: argparse.Namespace) -> int:
    """Validate all protocol, output, and derived-schema artifacts in a directory."""
    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"{colorize('Error:', Colors.RED)} Not a directory: {directory}")
        return 1

    try:
        schema_path = _find_schema_path(args.schema)
        schema = load_schema(schema_path)
    except FileNotFoundError as e:
        print(f"{colorize('Error:', Colors.RED)} {e}")
        return 1

    derived_schema = load_derived_schema(schema_path)

    schemas_dir = _resolve_schemas_dir(schema_path)
    derived_schemas: Dict[str, Dict[str, Any]] = {}
    if schemas_dir is not None:
        derived_schemas = _load_derived_schemas(schemas_dir)

    results = []
    parse_errors = 0  # Track files that failed to parse or load
    seen_files = set()
    # Note: ``schemas`` and ``development`` are intentionally no longer ignored.
    ignored_parts = {".reference", "legacy", ".git", ".venv", "node_modules"}

    # Walk directory to find matching files case-insensitively
    for file_path in directory.rglob("*"):
        if not file_path.is_file():
            continue
        if any(p in file_path.parts for p in ignored_parts):
            continue

        resolved_str = str(file_path.resolve())
        if resolved_str in seen_files:
            continue

        fname_lower = file_path.name.lower()

        # Meta-validate derived JSON Schema files
        if fname_lower.endswith(".schema.json"):
            seen_files.add(resolved_str)
            try:
                schema_data = load_json(file_path)
                valid, errors = _validate_json_schema(schema_data)
                results.append((file_path, valid, errors))
            except Exception as e:
                print(f"{colorize('Warning:', Colors.YELLOW)} Could not validate {_display_path(file_path)}: {e}")
                parse_errors += 1
            continue

        # Validate protocol files
        if fname_lower.endswith((".yaml", ".yml")) and "protocol" in fname_lower:
            seen_files.add(resolved_str)
            try:
                protocol = load_yaml(file_path)
                valid, errors = validate_protocol(protocol, schema)
                results.append((file_path, valid, errors))
            except Exception as e:
                print(f"{colorize('Warning:', Colors.YELLOW)} Could not validate {_display_path(file_path)}: {e}")
                parse_errors += 1
            continue

        # Validate output JSON files
        if fname_lower.endswith(".json"):
            output_type = None
            if "discovery" in fname_lower:
                output_type = "discovery"
            elif "plan" in fname_lower:
                output_type = "plan"
            elif "execution" in fname_lower or "changes" in fname_lower:
                output_type = "execution"
            elif "verification" in fname_lower:
                output_type = "verification"

            if output_type:
                seen_files.add(resolved_str)
                try:
                    output = load_json(file_path)
                    valid, errors = validate_agent_output(
                        output, output_type, schema, derived_schema
                    )
                    results.append((file_path, valid, errors))
                except Exception as e:
                    print(f"{colorize('Warning:', Colors.YELLOW)} Could not validate {_display_path(file_path)}: {e}")
                    parse_errors += 1
                continue

            # Validate derived artifacts (run-manifest, session-state,
            # final-report, rollback, handoff) against schemas/*.schema.json.
            derived_name = _derived_schema_name(fname_lower)
            if derived_name and derived_name in derived_schemas:
                seen_files.add(resolved_str)
                try:
                    output = load_json(file_path)
                    valid, errors = _validate_derived(output, derived_name, derived_schemas)
                    results.append((file_path, valid, errors))
                except Exception as e:
                    print(f"{colorize('Warning:', Colors.YELLOW)} Could not validate {_display_path(file_path)}: {e}")
                    parse_errors += 1
                continue

            if derived_name and derived_name not in derived_schemas:
                print(
                    f"{colorize('Warning:', Colors.YELLOW)} "
                    f"Derived schema missing for {_display_path(file_path)} (expected {derived_name}.schema.json)"
                )
                parse_errors += 1

    # Print results
    if not results:
        msg = f"FAIL/EMPTY — No expected RUP artifacts discovered in {_display_path(directory)}"
        print(f"{colorize(CROSS, Colors.RED)} {colorize(msg, Colors.BOLD)}")
        if parse_errors > 0:
            print(f"  {colorize(WARN, Colors.YELLOW)} Parse errors: {parse_errors}")
            return 1
        if args.allow_empty:
            print(f"{colorize('Note:', Colors.YELLOW)} --allow-empty enabled; treating empty scan as success.")
            return 0
        return 1

    print(f"\n{colorize('Validation Results', Colors.BOLD)}")
    print("=" * 50)

    total_valid = 0
    total_invalid = 0

    for file_path, valid, errors in results:
        print_result(file_path, valid, errors, args.verbose)
        if valid:
            total_valid += 1
        else:
            total_invalid += 1

    print("=" * 50)
    print(f"Total: {total_valid + total_invalid} files")
    print(f"  {colorize(CHECK, Colors.GREEN)} Valid: {total_valid}")
    print(f"  {colorize(CROSS, Colors.RED)} Invalid: {total_invalid}")
    if parse_errors > 0:
        print(f"  {colorize(WARN, Colors.YELLOW)} Parse errors: {parse_errors}")

    return 0 if (total_invalid == 0 and parse_errors == 0) else 1


def create_sample_output(output_type: str) -> Dict[str, Any]:
    """Create a sample output structure for testing."""
    samples = {
        'discovery': {
            "repo_metadata": {
                "name": "sample-repo",
                "primary_language": "python",
                "repo_type": "library",
                "loc": 5000,
                "file_count": 42
            },
            "languages": [
                {"name": "python", "percentage": 85.5, "lockfile_present": True}
            ],
            "tooling": {
                "test_framework": "pytest",
                "linter": "ruff"
            },
            "gaps": [
                {
                    "id": "TEST-001",
                    "category": "tests",
                    "severity": "high",
                    "title": "Low test coverage"
                }
            ],
            "risk_assessment": {
                "overall_risk": "medium",
                "technical_debt_score": 35,
                "production_readiness_score": 65
            }
        },
        'plan': {
            "backlog": [
                {
                    "id": "ITEM-001",
                    "priority": "P0",
                    "title": "Add missing tests"
                }
            ],
            "selected_items": ["ITEM-001"],
            "execution_order": ["ITEM-001"],
            "estimated_effort": {
                "total_minutes": 60,
                "confidence": "medium"
            }
        },
        'execution': {
            "changes": [
                {
                    "file_path": "tests/test_main.py",
                    "change_type": "create"
                }
            ],
            "commits": [
                {
                    "message": "test: add unit tests for main module",
                    "files": ["tests/test_main.py"]
                }
            ],
            "local_verification": {
                "tests": {"executed": True, "passed": True},
                "lint": {"executed": True, "passed": True}
            }
        },
        'verification': {
            "verification_results": {
                "overall_status": "passed"
            },
            "metrics": {
                "files_changed": 1,
                "lines_added": 50
            },
            "recommendations": {
                "ready_for_pr": True
            }
        }
    }
    
    return samples.get(output_type, {})


def cmd_sample(args: argparse.Namespace) -> int:
    """Generate sample output files for testing."""
    output_type = args.type
    output_path = Path(args.output) if args.output else Path(f"sample_{output_type}.json")
    
    sample = create_sample_output(output_type)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sample, f, indent=2)
    
    print(f"{colorize(CHECK, Colors.GREEN)} Created sample {output_type} output: {output_path}")
    return 0


def _add_common_args(p: argparse.ArgumentParser) -> None:
    """Add schema and verbose options to a subparser so they can appear after the subcommand.

    Using ``argparse.SUPPRESS`` as the default prevents a subparser that did not
    receive the option from overwriting the global value with its default.
    """
    p.add_argument(
        '--schema', '-s',
        type=Path,
        default=argparse.SUPPRESS,
        help='Path to rup-schema.json (default: same directory as script or RUP_SCHEMA_PATH)'
    )
    p.add_argument(
        '--verbose', '-v',
        action='store_true',
        default=argparse.SUPPRESS,
        help='Show all validation errors'
    )


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="RUP Protocol Validator v3.0.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Canonical examples:
  %(prog)s --schema protocol/rup-schema.json protocol rup-protocol.yaml
  %(prog)s --schema protocol/rup-schema.json output discovery.json discovery
  %(prog)s --schema protocol/rup-schema.json output plan.json plan
  %(prog)s --schema protocol/rup-schema.json all ./my-project
  %(prog)s --schema protocol/rup-schema.json sample discovery -o sample_discovery.json

Backwards-compatible examples:
  %(prog)s protocol rup-protocol.yaml --schema protocol/rup-schema.json
  %(prog)s all ./my-project --schema protocol/rup-schema.json
        """
    )

    # Global options are canonical; also accept them after subcommands for compatibility.
    parser.add_argument(
        '--schema', '-s',
        type=Path,
        default=Path(os.getenv('RUP_SCHEMA_PATH')) if os.getenv('RUP_SCHEMA_PATH') else None,
        help='Path to rup-schema.json (default: same directory as script or RUP_SCHEMA_PATH)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show all validation errors'
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Protocol validation
    protocol_parser = subparsers.add_parser('protocol', help='Validate a protocol YAML file')
    protocol_parser.add_argument('file', help='Path to protocol YAML file')
    _add_common_args(protocol_parser)

    # Output validation
    output_parser = subparsers.add_parser('output', help='Validate an agent output JSON file')
    output_parser.add_argument('file', help='Path to output JSON file')
    output_parser.add_argument(
        'type',
        choices=['discovery', 'plan', 'execution', 'verification'],
        help='Type of output'
    )
    _add_common_args(output_parser)

    # All validation
    all_parser = subparsers.add_parser('all', help='Validate all files in a directory')
    all_parser.add_argument('directory', help='Directory to scan')
    all_parser.add_argument(
        '--allow-empty',
        action='store_true',
        help='Allow zero discovered artifacts to validate (not for CI)'
    )
    _add_common_args(all_parser)

    # Sample generation
    sample_parser = subparsers.add_parser('sample', help='Generate sample output files')
    sample_parser.add_argument(
        'type',
        choices=['discovery', 'plan', 'execution', 'verification'],
        help='Type of sample to generate'
    )
    sample_parser.add_argument(
        '-o', '--output',
        help='Output file path'
    )
    _add_common_args(sample_parser)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 0
    
    commands = {
        'protocol': cmd_validate_protocol,
        'output': cmd_validate_output,
        'all': cmd_validate_all,
        'sample': cmd_sample,
    }
    
    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
