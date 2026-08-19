"""
State management, run manifest generation, and atomic persistence for RUP deterministic runtime.
"""
import hashlib
import json
import os
import tempfile
import datetime
import warnings
from pathlib import Path
from typing import Any, Dict, Optional, List
from .paths import RupPaths
from .models import RunManifest, SessionState
from .security import enforce_path_jail, safe_load_yaml, safe_load_json
from .command_runner import run_command
from .source_authority import CANONICAL_RUP_COMMIT, CANONICAL_PROTOCOL_VERSION


# Mapping from canonical artifact filename to the phase that produces it.
_ARTIFACT_PHASE_MAP = {
    "RUP_DISCOVERY.json": "discovery",
    "RUP_PLAN.json": "planning",
    "RUP_EXECUTION.json": "execution",
    "RUP_VERIFICATION.json": "verification",
    "RUP_FINAL_REPORT.json": "reporting",
    "run-manifest.json": "manifest",
    "run-manifest.json.sha256": "manifest",
    "session-state.json": "session",
    "RUP_DISCOVERY.md": "discovery",
    "RUP_PLAN.md": "planning",
    "RUP_EXECUTION.md": "execution",
    "RUP_VERIFICATION.md": "verification",
    "RUP_FINAL_REPORT.md": "reporting",
}


def _infer_artifact_type(filename: str) -> str:
    if filename.endswith(".json"):
        return "json"
    if filename.endswith(".md"):
        return "markdown"
    if filename.endswith(".sha256"):
        return "checksum"
    return "unknown"


def _infer_artifact_phase(filename: str) -> str:
    return _ARTIFACT_PHASE_MAP.get(filename, "unknown")


def _compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class StateManager:
    def __init__(self, paths: RupPaths, run_id: Optional[str] = None):
        self.paths = paths
        self.run_id = run_id or RunManifest.generate_run_id(str(paths.target_dir))
        self._session_state: Optional[SessionState] = None
        self._artifact_ledger: List[Dict[str, Any]] = []

    def _get_artifact_path(self, filename: str) -> Path:
        """Get the secure path for an artifact, placing state in .rup/ state directory."""
        return self.paths.get_state_path(filename)

    def save_json(self, data: Dict[str, Any], filename: str) -> Path:
        """Save state to a JSON file securely using atomic replacement."""
        out_path = self._get_artifact_path(filename)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        fd, temp_path = tempfile.mkstemp(dir=out_path.parent, prefix=".rup_tmp_", suffix=".json")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, out_path)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

        self._record_artifact(filename)
        return out_path

    def load_json(self, filename: str) -> Dict[str, Any]:
        """Load state from the controlled .rup/ state directory only.

        Runtime state is authoritative and must never be silently sourced from an
        untrusted target repository root. Use :meth:`migrate_legacy_state` for an
        explicit, audited import of legacy root-level artifacts.
        """
        in_path = self._get_artifact_path(filename)
        if not in_path.exists():
            return {}
        return safe_load_json(in_path)

    def load_protocol(self) -> Dict[str, Any]:
        """Load the canonical protocol definition."""
        proto_path = self.paths.protocol_dir / "rup-protocol.yaml"
        return safe_load_yaml(proto_path)

    def migrate_legacy_state(self) -> Dict[str, Any]:
        """Explicitly migrate legacy root-level RUP artifacts into .rup/.

        Each migrated file is validated as JSON, recorded with provenance, and
        written into the controlled state directory. The original root files are
        left untouched; this is a non-destructive import.
        """
        migrated = []
        source_root = self.paths.target_dir
        state_root = self.paths.state_dir
        state_root.mkdir(parents=True, exist_ok=True)

        legacy_names = [
            "RUP_DISCOVERY.json",
            "RUP_PLAN.json",
            "RUP_EXECUTION.json",
            "RUP_VERIFICATION.json",
            "RUP_FINAL_REPORT.json",
            "session-state.json",
            "run-manifest.json",
        ]

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if not now_str.endswith("Z"):
            now_str = now_str.replace("+00:00", "Z")

        for name in legacy_names:
            src = source_root / name
            if not src.exists() or src.is_dir():
                continue
            try:
                data = safe_load_json(src)
                if not isinstance(data, dict):
                    warnings.warn(
                        f"Legacy artifact {name} is not a JSON object; skipping.",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    continue
                dest = self._get_artifact_path(name)
                fd, temp_path = tempfile.mkstemp(
                    dir=dest.parent, prefix=".rup_migrate_", suffix=".json"
                )
                try:
                    with open(fd, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    os.replace(temp_path, dest)
                except Exception:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    raise

                self._record_artifact(name)
                migrated.append({
                    "artifact": name,
                    "source": str(src),
                    "migrated_at": now_str,
                    "run_id": self.run_id,
                    "sha256": _compute_sha256(dest),
                })
            except Exception as e:
                warnings.warn(f"Failed to migrate legacy artifact {name}: {e}", RuntimeWarning, stacklevel=2)

        # Persist provenance of the migration itself.
        if migrated:
            provenance_path = self._get_artifact_path("migration-provenance.json")
            provenance = {
                "run_id": self.run_id,
                "migrated_at": now_str,
                "artifacts": migrated,
            }
            fd, temp_path = tempfile.mkstemp(
                dir=provenance_path.parent, prefix=".rup_migrate_prov_", suffix=".json"
            )
            try:
                with open(fd, "w", encoding="utf-8") as f:
                    json.dump(provenance, f, indent=2)
                os.replace(temp_path, provenance_path)
            except Exception:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise
            self._record_artifact("migration-provenance.json")

        return {"migrated": migrated, "count": len(migrated)}

    def _get_target_commit(self) -> str:
        """Get target repository commit SHA if git is initialized."""
        try:
            rc, stdout, _ = run_command(["git", "rev-parse", "HEAD"], cwd=self.paths.target_dir)
            if rc == 0 and stdout.strip():
                return stdout.strip()
        except Exception as e:
            warnings.warn(f"Target commit query failed: {e}", RuntimeWarning, stacklevel=2)
        return "UNKNOWN_UNCOMMITTED"

    def _rebuild_artifact_ledger(self) -> None:
        """Ensure every artifact on disk in the state directory is recorded.

        Existing ledger entries are preserved so original creation timestamps are
        retained. Missing JSON and Markdown artifacts are appended using their
        current SHA-256 and modification time. This makes the final run manifest
        complete even when individual lifecycle phases are invoked with fresh
        ``StateManager`` instances.
        """
        if not self.paths.state_dir.exists():
            return

        existing = {entry["name"] for entry in self._artifact_ledger}
        for path in sorted(self.paths.state_dir.iterdir()):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            if path.suffix not in (".json", ".md", ".sha256"):
                continue
            if path.name in existing:
                continue

            try:
                sha256 = _compute_sha256(path)
            except Exception as e:
                warnings.warn(
                    f"Could not hash artifact {path.name}: {e}",
                    RuntimeWarning,
                    stacklevel=2,
                )
                sha256 = ""

            mtime = path.stat().st_mtime
            dt = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc)
            created_at = dt.isoformat()
            if not created_at.endswith("Z"):
                created_at = created_at.replace("+00:00", "Z")

            try:
                rel_path = str(path.relative_to(self.paths.state_dir))
            except ValueError:
                rel_path = str(path)

            self._artifact_ledger.append(
                {
                    "name": path.name,
                    "sha256": sha256,
                    "created_at": created_at,
                    "run_id": self.run_id,
                    "phase": _infer_artifact_phase(path.name),
                    "type": "json" if path.suffix == ".json" else "markdown",
                    "relative_path": rel_path,
                }
            )

    def generate_and_save_manifest(
        self,
        phases_completed: List[str],
        selected_items: List[str],
        execution_changes_count: int,
        verification_status: str
    ) -> Dict[str, Any]:
        """Create and persist a complete RunManifest artifact."""
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if not now_str.endswith("Z"):
            now_str = now_str.replace("+00:00", "Z")

        # Make sure every artifact written to .rup/ is represented in the manifest,
        # regardless of whether the same StateManager instance observed the write.
        self._rebuild_artifact_ledger()

        manifest = {
            "run_id": self.run_id,
            "created_at": now_str,
            "protocol_version": "3.0.0",
            "canonical_commit": "c3d6f70375db15d53db2fba76d70b5b7c9cf98bb",
            "target_path": str(self.paths.target_dir),
            "target_commit": self._get_target_commit(),
            "phases_completed": phases_completed,
            "selected_items": selected_items,
            "execution_changes_count": execution_changes_count,
            "verification_status": verification_status,
            "artifacts": [entry for entry in self._artifact_ledger if entry.get("name") != "run-manifest.json"],
        }
        # Save the final manifest once. The ledger intentionally excludes the
        # manifest itself so that the file bytes are stable and the self-hash
        # invariant is meaningful.
        self.save_json(manifest, "run-manifest.json")

        # Compute the hash of the final manifest and write it to a sidecar file.
        manifest_path = self._get_artifact_path("run-manifest.json")
        try:
            manifest_sha256 = _compute_sha256(manifest_path)
        except Exception as e:
            warnings.warn(f"Could not hash run-manifest.json: {e}", RuntimeWarning, stacklevel=2)
            manifest_sha256 = ""

        hash_path = self._get_artifact_path("run-manifest.json.sha256")
        fd, temp_path = tempfile.mkstemp(dir=hash_path.parent, prefix=".rup_tmp_", suffix=".sha256")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(manifest_sha256)
            os.replace(temp_path, hash_path)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

        # Record the manifest and its hash sidecar in the in-memory ledger for
        # any downstream consumers that need a complete artifact list.
        self._record_artifact("run-manifest.json.sha256")
        return manifest

    def update_session_state(self, phase: str) -> Dict[str, Any]:
        """Update and persist current lifecycle session state."""
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if not now_str.endswith("Z"):
            now_str = now_str.replace("+00:00", "Z")

        state = {
            "run_id": self.run_id,
            "current_phase": phase,
            "timestamp": now_str,
            "artifacts_generated": self._get_generated_artifacts()
        }
        self.save_json(state, "session-state.json")
        return state

    def _record_artifact(self, filename: str) -> None:
        """Record an artifact entry in the run ledger."""
        artifact_path = self._get_artifact_path(filename)
        try:
            sha256 = _compute_sha256(artifact_path)
        except Exception as e:
            warnings.warn(f"Could not hash artifact {filename}: {e}", RuntimeWarning, stacklevel=2)
            sha256 = ""

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if not now_str.endswith("Z"):
            now_str = now_str.replace("+00:00", "Z")

        # Store relative path inside the controlled state directory.
        try:
            rel_path = str(artifact_path.relative_to(self.paths.state_dir))
        except ValueError:
            rel_path = str(artifact_path)

        entry = {
            "name": filename,
            "sha256": sha256,
            "created_at": now_str,
            "run_id": self.run_id,
            "phase": _infer_artifact_phase(filename),
            "type": _infer_artifact_type(filename),
            "relative_path": rel_path,
        }
        # Replace any existing entry for this filename to keep the ledger current.
        self._artifact_ledger = [e for e in self._artifact_ledger if e["name"] != filename]
        self._artifact_ledger.append(entry)

    def _get_generated_artifacts(self) -> List[str]:
        artifacts = []
        for p in self.paths.state_dir.glob("*.json"):
            artifacts.append(p.name)
        for p in self.paths.state_dir.glob("*.md"):
            artifacts.append(p.name)
        return sorted(artifacts)
