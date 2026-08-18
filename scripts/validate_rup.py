#!/usr/bin/env python3
"""
RUP Protocol Validator v3.0.0

Validates RUP protocol YAML files and agent outputs against the JSON Schema.

Usage:
    python validate_rup.py protocol <protocol.yaml>
    python validate_rup.py output <output.json> <discovery|plan|execution|verification>
    python validate_rup.py all <directory>

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
    from jsonschema import Draft202012Validator, ValidationError
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


def load_schema(schema_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the RUP JSON Schema."""
    if schema_path is None:
        # Look for schema one level above (repo root)
        schema_path = Path(__file__).parent.parent / "rup-schema.json"
    
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    
    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load a YAML file."""
    _check_file_size(file_path)
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.load(f, Loader=LimitedAliasLoader)


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
        f"{prefix}{colorize('✗', Colors.RED)} {colorize(path, Colors.CYAN)}",
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
            validator = Draft202012Validator(schema)
            errors = list(validator.iter_errors(protocol_data))
            errors.insert(0, error)
            return False, errors

    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(protocol_data))
    return len(errors) == 0, errors


def validate_agent_output(
    output_data: Dict[str, Any],
    output_type: str,
    schema: Dict[str, Any]
) -> Tuple[bool, List[ValidationError]]:
    """Validate an agent output against the appropriate sub-schema."""
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
    
    if '$defs' not in schema or def_name not in schema['$defs']:
        raise ValueError(f"Schema definition not found: {def_name}")
    
    # Create a wrapper schema that references the definition
    # This allows the validator to properly resolve $refs
    wrapper_schema = {
        "$ref": f"#/$defs/{def_name}",
        "$defs": schema.get("$defs", {})
    }
    
    validator = Draft202012Validator(wrapper_schema)
    
    errors = list(validator.iter_errors(output_data))
    return len(errors) == 0, errors


def print_result(
    file_path: Path,
    valid: bool,
    errors: List[ValidationError],
    verbose: bool = False
) -> None:
    """Print validation result."""
    if valid:
        print(f"{colorize('✓', Colors.GREEN)} {colorize(str(file_path), Colors.BOLD)}: {colorize('Valid', Colors.GREEN)}")
    else:
        print(f"{colorize('✗', Colors.RED)} {colorize(str(file_path), Colors.BOLD)}: {colorize('Invalid', Colors.RED)}")
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
        schema = load_schema(args.schema)
        output = load_json(Path(args.file))
        
        valid, errors = validate_agent_output(output, args.type, schema)
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


def cmd_validate_all(args: argparse.Namespace) -> int:
    """Validate all protocol and output files in a directory."""
    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"{colorize('Error:', Colors.RED)} Not a directory: {directory}")
        return 1
    
    try:
        schema = load_schema(args.schema)
    except FileNotFoundError as e:
        print(f"{colorize('Error:', Colors.RED)} {e}")
        return 1
    
    results = []
    parse_errors = 0  # Track files that failed to parse
    
    # Find and validate protocol files
    for yaml_file in directory.glob("**/*.yaml"):
        if "protocol" in yaml_file.name.lower():
            try:
                protocol = load_yaml(yaml_file)
                valid, errors = validate_protocol(protocol, schema)
                results.append((yaml_file, valid, errors))
            except Exception as e:
                print(f"{colorize('Warning:', Colors.YELLOW)} Could not validate {yaml_file}: {e}")
                parse_errors += 1
    
    for yml_file in directory.glob("**/*.yml"):
        if "protocol" in yml_file.name.lower():
            try:
                protocol = load_yaml(yml_file)
                valid, errors = validate_protocol(protocol, schema)
                results.append((yml_file, valid, errors))
            except Exception as e:
                print(f"{colorize('Warning:', Colors.YELLOW)} Could not validate {yml_file}: {e}")
                parse_errors += 1
    
    # Find and validate output files
    output_patterns = [
        ("discovery", "**/discovery*.json"),
        ("plan", "**/plan*.json"),
        ("execution", "**/execution*.json"),
        ("execution", "**/changes*.json"),
        ("verification", "**/verification*.json"),
        ("verification", "**/report*.json"),
    ]
    
    for output_type, pattern in output_patterns:
        for json_file in directory.glob(pattern):
            try:
                output = load_json(json_file)
                valid, errors = validate_agent_output(output, output_type, schema)
                results.append((json_file, valid, errors))
            except Exception as e:
                print(f"{colorize('Warning:', Colors.YELLOW)} Could not validate {json_file}: {e}")
                parse_errors += 1
    
    # Print results
    if not results:
        print(f"{colorize('Warning:', Colors.YELLOW)} No files found to validate in {directory}")
        if parse_errors > 0:
            print(f"  {colorize('⚠', Colors.YELLOW)} Parse errors: {parse_errors}")
            return 1
        return 0
    
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
    print(f"  {colorize('✓', Colors.GREEN)} Valid: {total_valid}")
    print(f"  {colorize('✗', Colors.RED)} Invalid: {total_invalid}")
    if parse_errors > 0:
        print(f"  {colorize('⚠', Colors.YELLOW)} Parse errors: {parse_errors}")
    
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
    
    print(f"{colorize('✓', Colors.GREEN)} Created sample {output_type} output: {output_path}")
    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="RUP Protocol Validator v3.0.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s protocol rup-protocol.yaml
  %(prog)s output discovery.json discovery
  %(prog)s output plan.json plan
  %(prog)s all ./my-project
  %(prog)s sample discovery -o sample_discovery.json
        """
    )
    
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
    
    # Output validation
    output_parser = subparsers.add_parser('output', help='Validate an agent output JSON file')
    output_parser.add_argument('file', help='Path to output JSON file')
    output_parser.add_argument(
        'type',
        choices=['discovery', 'plan', 'execution', 'verification'],
        help='Type of output'
    )
    
    # All validation
    all_parser = subparsers.add_parser('all', help='Validate all files in a directory')
    all_parser.add_argument('directory', help='Directory to scan')
    
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
