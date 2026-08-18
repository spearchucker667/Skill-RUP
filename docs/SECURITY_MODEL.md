# Security Model

Skill-RUP implements robust guardrails to protect the host environment from agentic action.

## Path Jailing
`runtime/security.py` establishes `enforce_path_jail`, ensuring that no file path can exit the `target_dir`. It strictly utilizes `pathlib.Path.relative_to` to prevent string prefix bypassing.

## Command Execution
`runtime/command_runner.py` explicitly runs `subprocess.run(shell=False)` to prevent string injection attacks.

## Limited YAML Parsing
Configurations parse using `SafeLoader` or custom implementations (`LimitedAliasLoader`) to avoid YAML-bomb amplification.

## Security Scanning
On every push/PR, the repository tests itself via `bandit` to identify structural Python vulnerabilities, enforced in `security-scan.yml`.
