"""
Workspace (monorepo) detection and package graph for the RUP runtime.

Provides a real workspace package graph (audit P1-11):

- ``detect_workspace`` finds the workspace tool and enumerates packages from
  npm/yarn/pnpm workspaces, lerna, nx, turborepo, cargo workspaces, and go.work.
- Each package records its name, path, language, and internal dependencies.
- ``dependency_order`` returns a topological execution order.
- ``changed_packages`` maps a git diff to the set of affected packages so
  execution can be scoped to changed work.
"""
import json
import re
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .command_runner import run_command
from .security import read_jailed_text

_MAX_MANIFEST_BYTES = 2 * 1024 * 1024


def _read_text(root: Path, rel: str) -> Optional[str]:
    """Read a workspace manifest through the jailed reader."""
    try:
        return read_jailed_text(root, root / rel, max_bytes=_MAX_MANIFEST_BYTES)
    except (FileNotFoundError, PermissionError, ValueError):
        return None


def _load_json(text: Optional[str]) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _expand_globs(root: Path, patterns: List[str]) -> List[Path]:
    """Expand workspace glob patterns (e.g. ``packages/*``) into directories."""
    dirs: Set[Path] = set()
    for raw in patterns:
        pattern = (raw or "").strip()
        if not pattern or pattern.startswith("!"):
            continue
        # Relative patterns resolve against the workspace root.
        for match in root.glob(pattern):
            if match.is_dir():
                dirs.add(match.resolve())
    return sorted(dirs, key=lambda p: str(p))


def _classify_type(rel_path: str) -> str:
    """Classify a package type from its path (canonical enum: app/lib/service/tool)."""
    parts = rel_path.replace("\\", "/").split("/")
    for part in parts:
        if part in ("apps", "app", "applications", "services", "service", "microservices"):
            return "app" if part.startswith("app") else "service"
        if part in ("libs", "lib", "packages", "pkg", "core", "shared", "common", "utils"):
            return "lib"
        if part in ("tools", "tool", "scripts", "infra", "infrastructure"):
            return "tool"
    return "service"


def _inspect_package(root: Path, pkg_dir: Path, kind: Optional[str]) -> Tuple[Optional[str], List[str], str, str]:
    """Read one package's manifest: (name, internal dep names, language, type)."""
    rel = pkg_dir.relative_to(root).as_posix()

    # JavaScript/TypeScript package manifests.
    pkg_text = _read_text(root, f"{rel}/package.json")
    pkg = _load_json(pkg_text)
    if pkg:
        deps: List[str] = []
        for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            table = pkg.get(key)
            if isinstance(table, dict):
                deps.extend(str(k) for k in table.keys())
        return (
            str(pkg.get("name") or pkg_dir.name),
            deps,
            "typescript" if "typescript" in deps else "javascript",
            _classify_type(rel),
        )

    # Rust cargo workspace member.
    cargo_text = _read_text(root, f"{rel}/Cargo.toml")
    if cargo_text is not None:
        m_name = re.search(r"^\s*name\s*=\s*\"([^\"]+)\"", cargo_text, re.M)
        path_deps = [
            d
            for d in re.findall(r"^\s*([\w-]+)\s*=\s*\{\s*path\s*=", cargo_text, re.M)
        ]
        return (m_name.group(1) if m_name else pkg_dir.name, path_deps, "rust", _classify_type(rel))

    # Go module.
    go_mod = _read_text(root, f"{rel}/go.mod")
    if go_mod is not None:
        m_name = re.search(r"^\s*module\s+(\S+)", go_mod, re.M)
        return (m_name.group(1) if m_name else pkg_dir.name, [], "go", _classify_type(rel))

    # Fallback: directory name, no dependency edges.
    return (pkg_dir.name, [], "unknown", _classify_type(rel))


def detect_workspace(root: Path) -> Optional[Dict[str, Any]]:
    """Detect a workspace and return its package graph, or ``None``.

    Returned shape: ``{tool, kind, packages: [{name, path, language, type}],
    graph: {name: [internal dep names]}}``. ``tool`` is a canonical value where
    possible (``pnpm``/``lerna``/``nx``/``turborepo``) else ``custom``.
    """
    root = root.resolve()
    tool: Optional[str] = None
    kind: Optional[str] = None
    patterns: List[str] = []

    pnpm_text = _read_text(root, "pnpm-workspace.yaml")
    if pnpm_text is not None:
        tool, kind = "pnpm", "pnpm"
        for line in pnpm_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("-"):
                patterns.append(stripped[1:].strip().strip("'\""))
        if not patterns:
            patterns = ["packages/*"]

    root_pkg = _load_json(_read_text(root, "package.json"))
    if root_pkg and isinstance(root_pkg.get("workspaces"), list):
        tool = tool or "custom"
        kind = kind or "npm"
        patterns.extend(str(p) for p in root_pkg["workspaces"] if isinstance(p, str))

    lerna = _load_json(_read_text(root, "lerna.json"))
    if lerna and isinstance(lerna.get("packages"), list):
        tool, kind = "lerna", "lerna"
        patterns.extend(str(p) for p in lerna["packages"] if isinstance(p, str))

    if _read_text(root, "nx.json") is not None:
        tool, kind = "nx", "nx"
        patterns.extend(["packages/*", "libs/*"])
    if _read_text(root, "turbo.json") is not None:
        tool, kind = "turborepo", "turborepo"
        patterns.extend(["apps/*", "packages/*"])

    cargo_text = _read_text(root, "Cargo.toml")
    if cargo_text is not None and "[workspace]" in cargo_text:
        tool = tool or "custom"
        kind = kind or "cargo"
        m = re.search(r"members\s*=\s*\[(.*?)\]", cargo_text, re.S)
        if m:
            patterns.extend(item for item in re.findall(r"['\"]([^'\"]+)['\"]", m.group(1)))
        if not patterns:
            patterns = ["crates/*"]

    go_work = _read_text(root, "go.work")
    if go_work is not None:
        tool = tool or "custom"
        kind = kind or "go"
        for line in go_work.splitlines():
            stripped = line.strip()
            if stripped.startswith("use"):
                for part in stripped.split()[1:]:
                    if part not in (".", "./"):
                        patterns.append(part.rstrip("/"))

    # De-duplicate patterns while preserving order.
    seen: Set[str] = set()
    patterns = [p for p in patterns if not (p in seen or seen.add(p))]

    pkg_dirs = _expand_globs(root, patterns)
    if not pkg_dirs:
        return None

    packages: List[Dict[str, Any]] = []
    graph: Dict[str, List[str]] = {}
    for d in pkg_dirs:
        name, deps, language, ptype = _inspect_package(root, d, kind)
        rel = d.relative_to(root).as_posix()
        packages.append({"name": name, "path": rel, "language": language, "type": ptype})
        graph[name] = deps

    # Keep only internal dependency edges (names that resolve to packages).
    names = {p["name"] for p in packages}
    graph = {n: [d for d in deps if d in names] for n, deps in graph.items()}

    return {
        "tool": tool or "custom",
        "kind": kind,
        "packages": packages,
        "graph": graph,
    }


def dependency_order(
    names: List[str], graph: Dict[str, List[str]]
) -> List[str]:
    """Return ``names`` topologically sorted so dependencies come first.

    Cycles are broken with a warning and remaining items keep their input order
    (a cycle among selected items is separately rejected by planning).
    """
    remaining = set(names)
    ordered: List[str] = []
    while remaining:
        progressed = False
        for name in sorted(remaining):
            deps = [d for d in graph.get(name, []) if d in remaining]
            if not deps:
                ordered.append(name)
                remaining.discard(name)
                progressed = True
        if not progressed:
            cycle = sorted(remaining)
            warnings.warn(
                f"Workspace dependency cycle detected among: {', '.join(cycle)}; "
                "ordering by name.",
                RuntimeWarning,
                stacklevel=2,
            )
            ordered.extend(sorted(remaining))
            break
    return ordered


def changed_packages(
    root: Path, workspace: Dict[str, Any], base: str = "HEAD"
) -> Optional[List[str]]:
    """Return the packages containing working-tree changes.

    Uses ``git status --porcelain`` (not ``git diff``) so untracked files — the
    files RUP itself creates — count as changes. Returns ``None`` when the git
    status cannot be computed, ``["all"]`` when a root-level file changed (the
    whole workspace is affected), otherwise the sorted list of affected package
    names. ``base`` is accepted for interface compatibility but the working tree
    is the source of truth for scoping.
    """
    rc, stdout, _ = run_command(["git", "status", "--porcelain"], cwd=root)
    if rc != 0:
        return None
    files: List[str] = []
    for line in stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        # git quotes paths with special characters; renames are "old -> new".
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
            path = path[1:-1].replace('\\"', '"')
        if path:
            files.append(path)
    if not files:
        return []

    packages = workspace.get("packages", [])
    changed: Set[str] = set()
    for f in files:
        matched = False
        for p in packages:
            prefix = p["path"].rstrip("/") + "/"
            if f == p["path"] or f.startswith(prefix):
                changed.add(p["name"])
                matched = True
        if not matched:
            return ["all"]
    return sorted(changed)
