# Skill-RUP

Portable agent skill implementing RUP Protocol v3 for structured repository discovery, planning, execution, verification, and release-readiness workflows.

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![RUP Protocol](https://img.shields.io/badge/RUP-v3.0.0-green.svg)](https://github.com/spearchucker667/RUP-Protocol)

## What is Skill-RUP?
Skill-RUP is a portable agent skill that translates the canonical RUP (Repository Upgrade Protocol) into an agent-readable workflow and provides a deterministic repository-upgrade runtime. It acts as an execution engine that structures interactions between an AI agent and a target codebase.

## Why it exists
While the [RUP Protocol](https://github.com/spearchucker667/RUP-Protocol) dictates the conceptual process of discovering, planning, executing, and verifying changes, AI agents need a concrete implementation. Skill-RUP provides this implementation by defining the explicit `SKILL.md` interface and bundling a Python execution runtime to manage artifacts and validation deterministically.

## Relationship to RUP Protocol
- **RUP Protocol:** The canonical upstream protocol defining methodology.
- **Skill-RUP (this repo):** The downstream executable implementation.
If you need to change the semantic behavior of the RUP methodology, those changes must be made upstream.

## Core Capabilities
- **Deterministic State Tracking:** JSON-schema validated artifacts ensure agents do not lose context.
- **Path Jailing:** Security boundaries prevent agents from escaping the target repository workspace.
- **Capability Mapping:** Continuous validation against canonical requirements.
- **Automated Verification:** Seamlessly executes `pytest`, `npm test`, linters, and security scanners.

## RUP Lifecycle

```mermaid
flowchart LR
  D[Discovery] --> P[Planning]
  P --> E[Execution]
  E --> V[Verification]
  V --> R[Report / Handoff]
```

## Quick Start
To trigger the skill via your agent platform, instruct it to load `SKILL.md` as its primary prompt instruction set, or manually trigger the phases:

```bash
# Example: Run the RUP discovery phase on a target repository
python3 -m runtime.cli discovery --target /path/to/target-repo

# Full lifecycle (default: refuse target-controlled execution without a sandbox)
python3 -m runtime.cli all --target /path/to/repo

# Trusted environment without a sandbox:
python3 -m runtime.cli all --target /path/to/repo --sandbox off

# Adversarial content detected; explicit override to run target commands:
python3 -m runtime.cli all --target /path/to/repo --sandbox off --allow-exec
```

The runtime scans the target for adversarial instruction patterns before running
any target-controlled command (tests, build, lint, type check). By default
(`--sandbox required`) it refuses to execute those commands unless a sandbox is
detected; use `--sandbox off` only in a trusted environment, and `--allow-exec`
to explicitly opt into executing target commands when adversarial content is
present.

Execution captures a content baseline (HEAD plus per-path hashes of dirty files),
never mutates paths that were dirty at baseline, and records rollback as a single
set of platform-neutral operations (restore_content / remove_file /
restore_deleted / move_back) with per-backlog-item grouping. Revert executed
changes with:

```bash
python3 -m runtime.cli rollback --target /path/to/repo
```

Planning enforces dependency closure: a selected item is only admitted together
with its mandatory dependencies (recursively), or the dependent item is escalated
for explicit override. Each selected workstream carries a checkpoint (verification
method + success criteria), which execution enforces per item rather than only in
one global verification pass.

Monorepos (npm/yarn/pnpm workspaces, nx, turborepo, lerna, cargo workspaces,
go.work) are detected into a workspace package graph. Restrict execution to a
single package (with that package's own toolchain) or to packages containing
changes; scoped remediation files land inside the package directory:

```bash
python3 -m runtime.cli execute --target /path/to/repo --workspace packages/my-pkg
python3 -m runtime.cli run --target /path/to/repo --changed-packages
```

JS/TS tooling is resolved strictly offline (local `node_modules/.bin` shims,
then `npm exec --offline` / `pnpm exec` / `yarn exec`, then `npx --no-install`)
— the runtime never implicitly downloads tools over the network. Secret
scanning combines the portable built-in scanner with gitleaks/trufflehog when
installed, reports per-file coverage status, and fails closed on incomplete
coverage in strict mode.

## Installation
Clone the repository and install the minimal required dependencies:
```bash
git clone https://github.com/spearchucker667/Skill-RUP.git
cd Skill-RUP
pip install pyyaml jsonschema pytest
```

## Workflow Routing
The agent uses `SKILL.md` to route user intents to the appropriate sub-workflows defined in the `workflows/` directory.

## Architecture
The framework separates concerns across methodology (`protocol/`), agent instructions (`SKILL.md`), and deterministic execution (`runtime/`). See [Architecture](docs/ARCHITECTURE.md) for details.

## Safety and Trust Model
Skill-RUP executes untrusted AI-generated code. It implements jailed file I/O
(reads and writes resolve and verify containment against the target root, so
symlinks cannot escape), an adversarial-content trust gate before target
commands execute, a scrubbed subprocess environment, bounded/redacted command
output, and limited YAML parsing. **You must still run the agent in a sandboxed
or containerized environment.** See our [Security Model](docs/SECURITY_MODEL.md).

## Compatibility
Supports Python 3.11+ across macOS, Linux, and Windows/WSL2. See [Portability](docs/PORTABILITY.md) for the exact compatibility matrix.

## Generated Artifacts
The runtime synthesizes structured state across the lifecycle (e.g., `RUP_DISCOVERY.json`, `RUP_PLAN.json`). See [Artifact Contracts](docs/ARTIFACT_CONTRACTS.md).

## Documentation
- [Installation Guide](docs/INSTALL.md)
- [User Guide](docs/USER_GUIDE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [FAQ](docs/FAQ.md)
- [Contributor Guide](CONTRIBUTING.md)

## Security
For vulnerability disclosure, please see [SECURITY.md](SECURITY.md).

## Releases
For versioning details and distribution artifacts, see [RELEASES.md](docs/RELEASES.md).

## License and Attribution
Skill-RUP is released under the Apache-2.0 License. It incorporates material directly from the canonical RUP Protocol. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for attribution.
