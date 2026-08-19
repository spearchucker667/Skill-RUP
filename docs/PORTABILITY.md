# Portability Requirements

Skill-RUP aims for maximum portability across OS environments and Multi-Agent frameworks.

## Standard Python Libraries
The core `runtime/` engine strictly depends on the Python standard library with zero external dependencies where possible.
- Use `subprocess` securely for test and build tooling.
- Use `pathlib` for file routing and containment.
- Parsing YAML does rely on `PyYAML`, ensuring configuration portability.

## OS Agnostic
All OS operations abstract away bash/windows differences.
- Path traversal utilizes `pathlib.Path().relative_to()`.
- File writes leverage `os.replace` or atomic POSIX standard operations mapping correctly to Windows `os.replace`.

## Sandboxing
The RUP methodology forces execution to occur in containerized sandboxes whenever external dependencies are executed. Agents executing `run_command` via `execution.py` must operate in bounded execution pools, recommended to be run in a container or VM by the caller.
