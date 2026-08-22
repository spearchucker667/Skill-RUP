"""
Transactional rollback machinery for the RUP deterministic runtime.

Single source of truth for rollback: a list of semantic, platform-neutral
operations produced by the execution phase and consumed by:

- ``ReportingPhase`` (renders human-readable commands per platform), and
- the ``rollback`` CLI phase (applies the operations safely).

Operations are *semantic*, not shell commands:

    restore_content : restore a file to its pre-RUP content (backup or git HEAD)
    remove_file     : remove a file RUP created
    restore_deleted : restore a file RUP deleted (git HEAD)
    move_back       : reverse a rename RUP performed
    none            : nothing to revert

Every operation carries the owning backlog item and (where applicable) the
baseline content hash, so per-item rollback is possible and an omission can
never masquerade as a transfer.
"""
import shlex
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

from .command_runner import run_command
from .security import atomic_jailed_write, jailed_unlink

# Canonical operation identifiers; the single representation vocabulary.
ROLLBACK_OPS = ("restore_content", "remove_file", "restore_deleted", "move_back", "none")


def _quote_posix(path: str) -> str:
    return shlex.quote(path)


def _quote_powershell(path: str) -> str:
    # Single quotes are literal in PowerShell; embedded quotes are doubled.
    return "'" + path.replace("'", "''") + "'"


def render_rollback_commands(
    operations: List[Dict[str, Any]],
    platform: str = "posix",
) -> List[str]:
    """Render platform-neutral operations to human-readable commands.

    ``platform`` is ``"posix"`` (bash/sh) or ``"windows"`` (PowerShell).
    The rendered commands are a convenience view; the structured operations
    remain the authoritative representation consumed by the rollback executor.
    """
    quote = _quote_posix if platform == "posix" else _quote_powershell
    remove_cmd = "rm -f --" if platform == "posix" else "Remove-Item -Force -LiteralPath"
    commands: List[str] = ["# Rollback commands rendered from structured RUP rollback operations"]

    for op in operations:
        op_type = op.get("op")
        path = op.get("path", "")
        old_path = op.get("old_path")
        if op_type == "remove_file":
            commands.append(f"{remove_cmd} {quote(path)}")
        elif op_type in ("restore_content", "restore_deleted"):
            if op.get("backup_sha256"):
                commands.append(
                    f"# restore_content: backup {op['backup_sha256'][:12]} available; "
                    "run `python -m runtime.cli rollback` to apply it"
                )
            commands.append(f"git checkout -- {quote(path)}")
        elif op_type == "move_back" and old_path:
            commands.append(f"git mv -- {quote(path)} {quote(old_path)}")
        elif op_type not in (None, "none"):
            warnings.warn(
                f"Unknown rollback operation {op_type!r}; skipping command rendering",
                RuntimeWarning,
                stacklevel=2,
            )

    if not commands[1:]:
        commands.append("# No changes to revert")
    return commands


def _read_backup_bytes(backup_path: Path) -> bytes:
    with open(backup_path, "rb") as f:
        return f.read()


def _restore_from_backup(root: Path, state_dir: Path, op: Dict[str, Any]) -> Dict[str, Any]:
    """Restore a file from the content-addressed backup store."""
    path = op["path"]
    backup_sha = op.get("backup_sha256")
    backup_file = state_dir / "backups" / backup_sha
    if not backup_sha or not backup_file.is_file():
        return {
            "op": op.get("op"),
            "path": path,
            "status": "error",
            "reason": "No backup recorded; cannot restore without clobbering (use git checkout manually)",
        }
    try:
        data = _read_backup_bytes(backup_file)
        # surrogateescape round-trips arbitrary bytes losslessly.
        atomic_jailed_write(root, root / path, data.decode("utf-8", errors="surrogateescape"))
        return {"op": op.get("op"), "path": path, "status": "ok", "backup_sha256": backup_sha}
    except PermissionError as e:
        return {"op": op.get("op"), "path": path, "status": "error", "reason": str(e)}


def apply_rollback_operations(
    root: Path,
    operations: List[Dict[str, Any]],
    state_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Apply rollback operations safely and report per-operation results.

    - Paths are confined to ``root`` through the jailed primitives.
    - ``restore_content`` prefers the content-addressed backup; ``git checkout``
      is used only when no backup exists (and the repo is a git repo).
    - Nothing is ever removed/restored outside the jail.
    """
    root = root.resolve()
    state_dir = state_dir.resolve() if state_dir is not None else root / ".rup"
    results: List[Dict[str, Any]] = []
    applied = 0
    failed = 0

    for op in operations:
        op_type = op.get("op")
        path = op.get("path", "")
        if op_type in (None, "none"):
            results.append({"op": "none", "path": path, "status": "skipped"})
            continue
        if op_type not in ROLLBACK_OPS:
            results.append(
                {"op": op_type, "path": path, "status": "error", "reason": f"Unknown op {op_type!r}"}
            )
            failed += 1
            continue

        if dry_run:
            results.append({"op": op_type, "path": path, "status": "dry-run"})
            applied += 1
            continue

        if op_type == "restore_content":
            result = _restore_from_backup(root, state_dir, op)
            if result["status"] == "error":
                # Fall back to git restore of the tracked version.
                rc, _, stderr = run_command(["git", "checkout", "--", path], cwd=root)
                if rc != 0:
                    result["reason"] = result.get("reason", "") + f"; git checkout failed: {stderr.strip()}"
                    failed += 1
                else:
                    result["status"] = "ok"
                    result["via"] = "git"
                    applied += 1
            else:
                applied += 1
            results.append(result)
        elif op_type == "remove_file":
            try:
                jailed_unlink(root, root / path)
                results.append({"op": op_type, "path": path, "status": "ok"})
                applied += 1
            except PermissionError as e:
                results.append({"op": op_type, "path": path, "status": "error", "reason": str(e)})
                failed += 1
        elif op_type == "restore_deleted":
            rc, _, stderr = run_command(["git", "checkout", "HEAD", "--", path], cwd=root)
            if rc != 0:
                results.append(
                    {"op": op_type, "path": path, "status": "error", "reason": stderr.strip() or "git checkout failed"}
                )
                failed += 1
            else:
                results.append({"op": op_type, "path": path, "status": "ok"})
                applied += 1
        elif op_type == "move_back":
            old_path = op.get("old_path")
            if not old_path:
                results.append({"op": op_type, "path": path, "status": "error", "reason": "missing old_path"})
                failed += 1
                continue
            rc, _, stderr = run_command(["git", "mv", "--", path, old_path], cwd=root)
            if rc != 0:
                results.append(
                    {"op": op_type, "path": path, "old_path": old_path, "status": "error", "reason": stderr.strip() or "git mv failed"}
                )
                failed += 1
            else:
                results.append({"op": op_type, "path": path, "old_path": old_path, "status": "ok"})
                applied += 1

    return {
        "applied": applied,
        "failed": failed,
        "dry_run": dry_run,
        "results": results,
    }
