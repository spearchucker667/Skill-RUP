#!/usr/bin/env python3
"""
Deterministic packaging script for the RUP skill.

Produces a reproducible ZIP archive containing the skill tree under a top-level
`rup/` directory, an internal manifest with per-file SHA-256 hashes, and an
external SHA-256 checksum file.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Set


# Fixed ZIP timestamp for reproducibility (1980-01-01 00:00:00 is the earliest
# date supported by the ZIP format).
ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)

# Top-level skill directory inside the archive must match SKILL.md `name: rup`.
SKILL_DIR_NAME = "rup"

# Default distribution directory, relative to the skill root.
DEFAULT_DIST_DIR = "dist"


def _error(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)


def _deterministic_timestamp() -> str:
    """Return a reproducible manifest timestamp.

    Honors the ``SOURCE_DATE_EPOCH`` environment variable (standard for
    reproducible builds). Otherwise falls back to the Unix epoch.
    """
    source_date = os.getenv("SOURCE_DATE_EPOCH")
    if source_date is not None:
        try:
            ts = int(source_date)
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            pass
    return datetime.fromtimestamp(0, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_version(version: str) -> str:
    """Normalize and validate a semantic version string.

    Accepts ``3.0.0`` or ``v3.0.0`` and returns ``3.0.0``.
    """
    if not version:
        raise ValueError("version is required")
    version = version.strip()
    if version.startswith("v") or version.startswith("V"):
        version = version[1:]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"version must be semantic (MAJOR.MINOR.PATCH), got: {version}")
    return version


def _should_include(path: Path, root: Path, ignored: Set[str]) -> bool:
    rel_parts = path.relative_to(root).parts
    if not rel_parts:
        return True
    if any(part in ignored for part in rel_parts):
        return False
    if path.is_file() and path.name.endswith(".pyc"):
        return False
    return True


def hash_file(filepath: Path) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _zip_info(arcname: str, is_dir: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(filename=arcname, date_time=ZIP_DATE_TIME)
    if is_dir:
        info.compress_type = zipfile.ZIP_STORED
        info.external_attr = (0o40755 << 16) | 0x10
    else:
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
    return info


def package_skill(
    root_dir: Path,
    out_path: Path,
    version: str,
) -> Dict[str, str]:
    """Create a deterministic skill package archive.

    Returns the manifest mapping (excluding the manifest itself).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ignored = {
        ".git",
        ".github",
        ".reference",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".freebuff",
        ".DS_Store",
        "dist",
        "build",
        "node_modules",
        ".work orders",
        ".tests",
    }

    manifest: Dict[str, str] = {}

    # Walk the source tree in sorted order for reproducibility.
    with zipfile.ZipFile(out_path, "w") as zf:
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = sorted(d for d in dirnames if _should_include(Path(dirpath) / d, root_dir, ignored))
            filenames = sorted(f for f in filenames if _should_include(Path(dirpath) / f, root_dir, ignored))

            current = Path(dirpath)
            rel_dir = current.relative_to(root_dir)

            # Add directory entries for non-root directories.
            if rel_dir.parts:
                arc_dir = f"{SKILL_DIR_NAME}/{rel_dir.as_posix()}/"
                zf.writestr(_zip_info(arc_dir, is_dir=True), b"")

            for filename in filenames:
                file_path = current / filename
                rel_path = file_path.relative_to(root_dir)
                arcname = f"{SKILL_DIR_NAME}/{rel_path.as_posix()}"

                # Do not pack the output archive itself if it lives under root.
                if file_path.resolve() == out_path.resolve():
                    continue

                data = file_path.read_bytes()
                zf.writestr(_zip_info(arcname), data)
                manifest[arcname] = hashlib.sha256(data).hexdigest()

        # Build and include the manifest before closing the archive.
        created_at = _deterministic_timestamp()
        package_manifest = {
            "name": SKILL_DIR_NAME,
            "version": version,
            "created_at": created_at,
            "files": dict(sorted(manifest.items())),
        }
        manifest_bytes = json.dumps(package_manifest, indent=2, sort_keys=True).encode("utf-8")
        manifest_arcname = f"{SKILL_DIR_NAME}/manifest.json"
        zf.writestr(_zip_info(manifest_arcname), manifest_bytes)

    # Hash the completed archive.
    archive_sha256 = hash_file(out_path)
    sha_path = out_path.with_suffix(out_path.suffix + ".sha256")
    sha_path.write_text(f"{archive_sha256}  {out_path.name}\n", encoding="utf-8")

    print(f"Packaged {len(manifest)} files into {out_path}")
    print(f"Archive SHA-256: {archive_sha256}")
    print(f"Checksum written to {sha_path}")

    return manifest


def verify_package(out_path: Path) -> int:
    """Verify an existing package manifest and hashes."""
    if not out_path.exists():
        _error(f"Package not found: {out_path}")
        return 1

    with zipfile.ZipFile(out_path, "r") as zf:
        names = zf.namelist()
        if not all(name.startswith(f"{SKILL_DIR_NAME}/") for name in names):
            _error("Archive does not use a top-level 'rup/' skill directory")
            return 1

        if f"{SKILL_DIR_NAME}/manifest.json" not in names:
            _error("Archive is missing manifest.json")
            return 1

        try:
            manifest = json.loads(zf.read(f"{SKILL_DIR_NAME}/manifest.json").decode("utf-8"))
        except Exception as e:
            _error(f"Could not parse manifest.json: {e}")
            return 1

        expected_files = manifest.get("files", {})
        verified = 0
        failed = 0
        for arcname, expected_sha in sorted(expected_files.items()):
            if arcname not in names:
                _error(f"Manifest references missing file: {arcname}")
                failed += 1
                continue
            actual = hashlib.sha256(zf.read(arcname)).hexdigest()
            if actual != expected_sha:
                _error(f"Hash mismatch for {arcname}: expected {expected_sha}, got {actual}")
                failed += 1
            else:
                verified += 1

        # The manifest itself is not listed in its own "files" map, so verify it
        # separately by recomputing its bytes deterministically.
        recomputed = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        if hashlib.sha256(zf.read(f"{SKILL_DIR_NAME}/manifest.json")).hexdigest() != hashlib.sha256(recomputed).hexdigest():
            _error("Manifest.json is not canonically formatted")
            failed += 1

    if failed:
        print(f"Package verification FAILED: {failed} issue(s)", file=sys.stderr)
        return 1

    print(f"Package verification PASSED: {verified} file hash(es) verified")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic RUP skill packager")
    parser.add_argument(
        "--version",
        default=os.getenv("RUP_SKILL_VERSION", "3.0.0"),
        help="Semantic version for the package (default: 3.0.0 or RUP_SKILL_VERSION)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output archive path (default: dist/rup-skill-<version>.zip)",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Skill source root directory (default: repository root)",
    )
    parser.add_argument(
        "--check",
        "--verify",
        dest="verify",
        action="store_true",
        help="Verify the produced package instead of building",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    try:
        version = normalize_version(args.version)
    except ValueError as e:
        _error(str(e))
        return 1

    root_dir = Path(args.root).resolve() if args.root else Path(__file__).parent.parent.resolve()

    if args.output:
        out_path = Path(args.output).resolve()
    else:
        out_path = (root_dir / DEFAULT_DIST_DIR / f"rup-skill-v{version}.zip").resolve()

    # Enforce that the output lives inside the distribution directory under root.
    dist_dir = (root_dir / DEFAULT_DIST_DIR).resolve()
    try:
        out_path.relative_to(dist_dir)
    except ValueError:
        _error(f"Output path must be inside {dist_dir}; got {out_path}")
        return 1

    if args.verify:
        return verify_package(out_path)

    package_skill(root_dir, out_path, version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
