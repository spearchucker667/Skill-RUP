# Skill-RUP

**Skill-RUP** is a production-grade, agent-native implementation of the [RUP Protocol v3.0.0](https://github.com/spearchucker667/RUP-Protocol).

It transforms the machine-readable RUP specification into an executable, portable skill that can be run deterministically.

## Architecture

- **`SKILL.md`**: The primary entry point for agent workflows.
- **`runtime/`**: The deterministic Python implementation for calculating line counts, generating execution state, parsing diffs, running tests, and managing phases.
- **`workflows/`**: Phase and workstream guidelines extracted automatically from the canonical `rup-protocol.yaml`.
- **`schemas/`**: Strict JSON schemas extracted directly from the canonical `rup-schema.json`.
- **`protocol/`**: The authoritative RUP v3 protocol sources.

## Phases

Skill-RUP handles the standard lifecycle:
1. **Discovery**: Runs `runtime.cli discovery` to detect codebase state and identify genuine gaps.
2. **Plan**: Runs `runtime.cli plan` to translate gaps into a prioritized backlog.
3. **Execute**: Runs `runtime.cli execute` to verify real uncommitted changes.
4. **Verify**: Runs `runtime.cli verify` to execute actual tests and evaluate readiness.
5. **Report**: Runs `runtime.cli report` to emit the final `RUP_FINAL_REPORT.md`.

## Documentation

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for how to use this skill, and [docs/INSTALL.md](docs/INSTALL.md) for setup instructions.
