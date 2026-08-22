"""
Offline tool resolution for JavaScript/TypeScript tooling (audit P1-18).

The runtime must never acquire tooling over the network implicitly. This
module resolves commands for JS toolchain binaries (jest, vitest, mocha,
eslint, tsc) with a strictly-offline preference order:

1. the package-local ``node_modules/.bin/<tool>`` shim (absolute path);
2. the detected package manager's offline exec (``npm exec --offline``,
   ``pnpm exec``, ``yarn exec``) — none of these installs by default;
3. ``npx --no-install`` (npx refuses to install without ``--install``);
4. a bare binary on ``PATH`` (already installed globally; no network).

If none of these resolve, the returned command is the bare tool name and the
caller's availability gate reports it unavailable — never silently fetched.
"""
import os
import shutil
from pathlib import Path
from typing import List, Optional


def _detect_package_manager(root: Path) -> Optional[str]:
    """Infer the JS package manager from lockfiles present at ``root``."""
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "package-lock.json").exists():
        return "npm"
    return None


def _windows() -> bool:
    """Platform check isolated so tests can patch it without mutating ``os.name``
    (which would also change pathlib's Path class dispatch).
    """
    return os.name == "nt"


def _local_bin_candidates(root: Path, tool: str) -> List[str]:
    """Candidate shim paths for a tool in ``root/node_modules/.bin``.

    On Windows the npm/yarn/pnpm shims are ``<tool>.cmd`` wrappers; on POSIX
    they are extension-less shell scripts. ``subprocess`` on Windows executes
    ``.cmd`` shims when given the explicit path.
    """
    bin_dir = root / "node_modules" / ".bin"
    names = [f"{tool}.cmd", f"{tool}.exe", tool] if _windows() else [tool]
    return [str(bin_dir / name) for name in names]


def resolve_js_tool(root: Path, tool: str, args: Optional[List[str]] = None) -> List[str]:
    """Return an offline-safe argv for running a JS tool from ``root``."""
    args = args or []

    for candidate in _local_bin_candidates(root, tool):
        if Path(candidate).is_file():
            return [candidate, *args]

    pkg_mgr = _detect_package_manager(root)
    if pkg_mgr == "pnpm":
        return ["pnpm", "exec", tool, *args]
    if pkg_mgr == "yarn":
        return ["yarn", "exec", tool, *args]
    if pkg_mgr == "npm":
        return ["npm", "exec", "--offline", "--", tool, *args]

    # No lockfile: fall back to npx in no-install mode, then PATH.
    if shutil.which("npx"):
        return ["npx", "--no-install", tool, *args]
    return [tool, *args]
