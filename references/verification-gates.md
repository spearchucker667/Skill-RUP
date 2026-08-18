# Verification Gates - Canonical Reference

This document outlines the canonical verification gates and rules for the Verification phase of RUP Protocol v3.0.0.

## Phase 4: Verification

### Core Principle

**Never claim a command/test/security scan was executed unless it actually ran.**

This is a critical guardrail. The verification phase MUST execute all required gates and report accurate results. If a gate cannot be executed (missing dependencies, unavailable tools), it MUST be marked as `executed: false` and the overall certification MUST NOT be `passed`.

### Centralized Command Execution

**Purpose**: Ensure consistent, deterministic command execution across all platforms.

**Rules**:
- All commands MUST be executed through `command_runner.py`
- Use `sys.executable` for Python commands to ensure the same Python interpreter
- Set appropriate timeouts for each command type
- Bound command output to prevent log flooding (default: 1000 lines)
- Capture exit codes accurately
- Normalize line endings across platforms (Linux, macOS, Windows)

**Command Categories and Timeouts**:
- **Lint**: 120 seconds (most linters are fast)
- **Test**: 300 seconds per run (tests can be slow)
- **Build**: 600 seconds (builds can be very slow)
- **Type check**: 180 seconds
- **Security scan**: 300 seconds
- **Default**: 300 seconds

### Gate 4.1: Test Verification (3-run & Flakiness Detection)

**Purpose**: Verify that tests pass consistently, detecting flaky tests.

**Rules**:
- Execute tests THREE times consecutively
- Only consider tests `passed` if ALL THREE runs pass
- Report test statistics:
  - `total`: total number of tests
  - `passed`: number of passing tests (all 3 runs)
  - `failed`: number of failing tests (any run)
  - `skipped`: number of skipped tests
  - `flaky`: number of tests that passed in some runs but failed in others
  - `execution_time_seconds`: average execution time

**Flakiness Detection**:
- A test is flaky if it passes in at least one run but fails in at least one other run
- Flaky tests MUST be reported and flagged
- Flaky tests should NOT block certification but should be flagged as warnings

**Test Frameworks Supported**:
- Python: pytest, unittest
- JavaScript/TypeScript: jest, vitest, mocha
- Go: go test
- Rust: cargo test

**Required Outputs**:
```json
{
  "tests": {
    "executed": true,
    "framework": "pytest",
    "total": 42,
    "passed": 40,
    "failed": 2,
    "skipped": 0,
    "flaky": 0,
    "execution_time_seconds": 12.5,
    "passed": true/false
  }
}
```

### Gate 4.2: Lint Verification

**Purpose**: Verify that code passes linting checks.

**Rules**:
- Execute all detected linters
- Report violation counts (before and after if applicable)
- Lint passes if zero violations OR violation delta is negative
- Capture actual lint output for debugging

**Linters Supported**:
- Python: ruff, flake8, black (formatting)
- JavaScript/TypeScript: eslint, prettier (formatting)
- Go: golangci-lint
- Rust: clippy

**Required Outputs**:
```json
{
  "lint": {
    "executed": true,
    "linter": "ruff",
    "violations_before": 15,
    "violations_after": 0,
    "passed": true/false,
    "output": "..."
  }
}
```

### Gate 4.3: Security Verification

**Purpose**: Verify that security checks pass.

**Rules**:
- Execute secret scanning on all changes
- Execute dependency vulnerability scanning if lockfiles exist
- Execute SAST (Static Application Security Testing) if available
- Never expose secrets in output
- All secrets found MUST be redacted in reports

**Security Scanners**:
- Secret scanning: built-in secret pattern matching
- Dependency scanning: if lockfiles present, scan for known CVEs
- SAST: bandit (Python), semgrep (multi-language)

**Required Outputs**:
```json
{
  "security": {
    "executed": true,
    "secret_scan": {
      "executed": true,
      "secrets_found": 0,
      "passed": true
    },
    "dependency_scan": {
      "executed": true/false,
      "vulnerabilities_found": 0,
      "passed": true/false
    },
    "sast": {
      "executed": true/false,
      "issues_found": 0,
      "passed": true/false
    },
    "passed": true/false
  }
}
```

### Gate 4.4: Build & Type Verification

**Purpose**: Verify that code builds and passes type checking.

**Rules**:
- Execute build commands if build configuration exists
- Execute type checking if type checker is configured
- Report build success/failure
- Report type checking violations

**Build Systems**:
- Python: poetry build, pip install, etc.
- JavaScript/TypeScript: npm run build, tsc
- Go: go build
- Rust: cargo build

**Type Checkers**:
- Python: mypy
- TypeScript: tsc

**Required Outputs**:
```json
{
  "build": {
    "executed": true/false,
    "build_system": "poetry",
    "success": true/false,
    "output": "..."
  },
  "type_check": {
    "executed": true/false,
    "type_checker": "mypy",
    "violations": 0,
    "passed": true/false
  }
}
```

### Git Diff Numstat

**Purpose**: Accurately report changes made during execution.

**Rules**:
- Use `git diff --numstat` to count lines added and removed
- Report per-file and aggregate statistics
- Never report changes that weren't actually made

**Required Outputs**:
```json
{
  "git_stats": {
    "files_changed": 5,
    "lines_added": 247,
    "lines_removed": 89,
    "file_details": {
      "src/main.py": {"added": 50, "removed": 20},
      "tests/test_main.py": {"added": 197, "removed": 69}
    }
  }
}
```

### Strict Certification

**Purpose**: Ensure certification is only granted when all required gates are executed and passed.

**Rules**:
- If `strict` mode is enabled (default: true):
  - All required gates MUST be executed
  - All required gates MUST pass
  - Otherwise certification is `failed`
- If `strict` mode is disabled:
  - Unexecuted gates are marked `executed: false`
  - Certification can be `passed_with_unexecuted_gates`
  - This is NOT recommended for production use

**Required Gates**:
- tests (required if test framework detected)
- lint (required if linter detected)
- security (always required)
- build (required if build system detected)
- type_check (required if type checker detected)

**Certification Levels**:
- `passed`: All required gates executed and passed
- `passed_with_unexecuted_gates`: Some optional gates not executed, all executed gates passed (strict mode off)
- `failed`: At least one required gate failed or was not executed (strict mode on)

**Required Outputs**:
```json
{
  "verification_results": {
    "overall_status": "passed|passed_with_unexecuted_gates|failed",
    "strict_mode": true,
    "required_gates_executed": true,
    "required_gates_passed": true
  },
  "metrics": {
    "files_changed": 5,
    "lines_added": 247,
    "lines_removed": 89
  },
  "recommendations": {
    "ready_for_pr": true/false,
    "requires_manual_review": true/false,
    "rollback_instructions": "..."
  }
}
```
