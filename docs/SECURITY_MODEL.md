# Security Model

Skill-RUP models the **target repository as an untrusted trust domain**. The
runtime applies defense in depth: path jailing on every repository I/O,
adversarial-content screening before target-controlled commands execute, a
scrubbed subprocess environment, bounded and redacted command output, and
state isolation. The controls below reflect the implementation at HEAD after
the 2026-08-21 P0 remediation pass; remaining limits are stated explicitly.

## 1. Path Jailing (RUP-SEC-001)

`runtime/security.py` establishes `enforce_path_jail`, which resolves both the
root and the candidate and verifies containment with
`pathlib.Path.relative_to`. A single resolve call is not a system-wide
boundary, so all repository I/O goes through jailed primitives:

- `iter_jailed_files(root, skip_dirnames=None)` — walks the tree without
  following directory symlinks. File symlinks whose resolved target escapes
  the root are skipped with a warning and never read; internal symlinks are
  yielded as their resolved target (deduplicated). Directory symlinks are
  never traversed.
- `open_jailed_read(root, target)` / `read_jailed_text(...)` — open/read only
  when the resolved path (including the final symlink) is inside `root`.
- `atomic_jailed_write(root, target, content)` — refuses to write through an
  existing file symlink or through a parent-directory symlink escaping the
  root; writes are atomic (tempfile + `os.replace`) inside the verified
  parent.
- `jailed_mkdir(...)` / `jailed_unlink(...)` — directory creation and removal
  with the same containment check, so cleanup can never delete external files.

Every target-repository read and write in the runtime (inventory, discovery,
verification, redaction callers, provenance hashing, tool detection, state
migration, and all execution workstream file generation) routes through these
primitives. `RupPaths` resolves and verifies both custom and default
(`<target>/.rup`) state directories at initialization and re-verifies the
state root on every access, so a pre-existing or swapped `.rup` symlink cannot
redirect state writes outside the target.

**Remaining limit:** these are check-then-use guards. Full TOCTOU resistance
against a concurrent attacker who swaps paths between check and use is not
implemented; run the runtime in a sandbox/container for strong hostile-repo
protection.

## 2. Command Execution (RUP-SEC-002)

`runtime/command_runner.py` runs `subprocess.run(shell=False)` with an explicit
argv list, an absolute `cwd`, and a timeout. `shell=False` prevents shell-string
injection; it does **not** by itself protect the host from a hostile
repository. The additional controls are:

- **Adversarial-content trust gate.** `scan_repository_for_threats()` runs
  over the jailed project tree *before* any target-controlled command. In the
  full lifecycle the scan runs immediately after Discovery; in Verification
  the prompt-injection scan is the first gate; in Execution the same gate
  precedes baseline-coverage and local-verification runs. If adversarial
  instruction patterns are found and `--allow-exec` was not supplied, the
  runtime refuses to continue or records the executable gates as `blocked`.
- **Sandbox policy.** `--sandbox {required,preferred,off}` (default
  `required`). Under `required`, target-controlled commands are refused when
  no sandbox is detected (container markers, `RUP_SANDBOXED`, or
  `bwrap`/`firejail` on PATH). `preferred` warns and proceeds; `off` proceeds
  silently (trusted environments only). Detection is deliberately
  conservative: an undetected sandbox refuses rather than silently proceeds.
- **Scrubbed environment.** The subprocess environment is reduced to an
  allowlist (PATH, home/temp, Windows system keys, locale, package-manager
  config prefixes). Host credentials, CI secrets, and tokens are not
  inherited by target-controlled commands.
- **Bounded output.** Captured stdout/stderr are capped (default 512 KiB per
  stream) with an explicit truncation marker.
- **Secret redaction.** Captured stdout/stderr are passed through
  `redact_secrets()` before they enter structured results or artifacts.
- **Offline tooling (P1-18).** JS/TS binaries resolve strictly offline — local
  `node_modules/.bin` shims, `npm exec --offline`, `pnpm exec` / `yarn exec`,
  `npx --no-install`, or a bare PATH binary. No tool is ever implicitly
  downloaded; unresolvable tools are reported `unavailable`, not fetched.

**Remaining limits:** there is no network egress restriction and no
process-group teardown guarantee. For hostile repositories, run inside a
sandboxed/containerized environment and review `--allow-exec`/`--sandbox`
decisions deliberately.

## 3. State Isolation

All runtime state lives under `<target>/.rup/` (or a verified in-target
`--state-dir`). Root-level `RUP_*` artifacts in the target are never trusted;
they are imported only through the explicit `migrate` command, which now reads
them through the jailed reader. State files are written atomically
(tempfile + `os.replace`) and recorded in an artifact ledger with SHA-256
hashes.

## 4. Limited Parsing

Configurations parse with `yaml.SafeLoader`-derived loaders
(`LimitedAliasLoader`, alias expansion capped at 50, arbitrary object tags
rejected) and JSON with size guardrails, preventing YAML-bomb amplification
and object-construction attacks.

## 5. Secret and Adversarial Scanning

- `runtime/redaction.py` scans repository files for AWS/ASIA keys, GitHub
  (classic and fine-grained), GitLab PATs, npm/PyPI tokens, Stripe live keys,
  Google API keys, private keys, JWTs, Slack tokens, and generic
  high-entropy assignments, and redacts them from captured command output.
- Secret scans report structured coverage status (`files_scanned`,
  `files_skipped`, `scan_errors`, `complete`): zero findings never implies
  "clean" when files were too large or unreadable, and strict mode fails the
  gate on incomplete coverage. When gitleaks or trufflehog is installed, its
  findings are merged in; the built-in scanner remains the portable fallback.
- `runtime/security.py` scans repository content for adversarial instruction
  patterns (`scan_content_for_threats`) used by the pre-execution trust gate.

## 6. CI Self-Testing

On every push/PR the repository tests itself via `bandit` and CodeQL
(`security-scan.yml`), runs the full pytest suite across Ubuntu/macOS/Windows,
and validates packaging/provenance/capability invariants.
