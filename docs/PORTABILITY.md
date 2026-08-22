# Portability Requirements

Skill-RUP aims for maximum portability across OS environments and Multi-Agent frameworks.

## Standard Python Libraries

The core `runtime/` engine strictly depends on the Python standard library plus
a small pinned set of runtime dependencies (`PyYAML`, `jsonschema`, `rich`; see
`requirements-ci.txt`). Use `subprocess` with argv arrays (`shell=False`) for
test and build tooling, and `pathlib` for file routing and containment.

## OS Agnostic

The runtime is tested on Ubuntu, macOS, and Windows via GitHub Actions, and OS
differences are handled in the runtime, not by shell strings:

- Path traversal uses `pathlib.Path().relative_to()` after `resolve()` on every
  jailed read/write (`runtime/security.py`).
- File writes use atomic tempfile + `os.replace`, which maps correctly on
  Windows.
- **Rollback is platform-neutral by design**: the execution phase records
  semantic operations (`restore_content` / `remove_file` / `restore_deleted` /
  `move_back`) that never reference shell syntax. Human-readable commands are
  *rendered* from those operations per platform (`runtime/rollback.py`:
  POSIX `sh` vs Windows PowerShell), and the `rollback` CLI phase applies the
  operations directly without a shell. Git operations go through `git` argv
  commands, which Git for Windows provides natively.
- JS/TS tooling is resolved offline with platform-aware shim handling
  (`node_modules/.bin/<tool>.cmd` on Windows) via `runtime/tool_resolution.py`.

## Sandboxing

Target-controlled commands (tests, build, lint, type check) are gated by an
adversarial-content scan and a sandbox policy. The CLI accepts
`--sandbox required|preferred|off` (default `required`): in a containerized or
VM environment the caller should run the runtime there and the policy detects
it; use `--sandbox off` only in a trusted environment. `--allow-exec` is the
explicit override for the adversarial-content gate. Command execution scrubs
the environment to an allowlist, bounds captured output, and redacts secrets.

## Offline Tooling

The runtime never implicitly acquires tooling over the network. JavaScript /
TypeScript binaries resolve to local `node_modules/.bin` shims, `npm exec
--offline`, `pnpm exec` / `yarn exec`, or `npx --no-install` — in that order —
and are reported `unavailable` when none is present rather than fetched.
