#!/usr/bin/env python3
"""
Rebuild Skill-RUP provenance manifests from the pinned upstream RUP-Protocol commit.

This script produces:

* ``provenance/canonical-source-manifest.json`` — maps every upstream path/blob
  to its local destination path in Skill-RUP.
* ``provenance/transfer-manifest.json`` — records how each upstream source was
  transferred (exact_copy/derived/translated/omitted), the transformation tool,
  destination hashes, parity tests, and rationale.
* ``provenance/source-manifest.json`` — top-level provenance index pointing to
  the two manifests above.
* ``provenance/source-manifest.sha256`` — SHA-256 checksum of the canonical
  source manifest.

With ``--check`` the script reconstructs the upstream tree and verifies every
recorded transfer without writing new manifest files.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

from runtime.provenance import (
    CANONICAL_RUP_COMMIT,
    CANONICAL_RUP_REPO,
    build_canonical_source_manifest,
    build_transfer_manifest,
    clone_upstream_commit,
    verify_transfer_manifest,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild Skill-RUP provenance manifests from the pinned upstream commit."
    )
    parser.add_argument(
        "--upstream-dir",
        type=Path,
        help=(
            "Use an existing upstream RUP-Protocol checkout instead of cloning. "
            "The checkout must be at the pinned canonical commit."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Verify existing manifests against the upstream source without "
            "writing new files. Implies loading already-written manifests."
        ),
    )
    parser.add_argument(
        "--commit",
        default=CANONICAL_RUP_COMMIT,
        help="Upstream commit to reconstruct (default: pinned canonical commit).",
    )
    args = parser.parse_args()

    prov_dir = ROOT / "provenance"
    prov_dir.mkdir(parents=True, exist_ok=True)

    canonical_path = prov_dir / "canonical-source-manifest.json"
    transfer_path = prov_dir / "transfer-manifest.json"
    source_path = prov_dir / "source-manifest.json"
    sha_path = prov_dir / "source-manifest.sha256"

    if args.check:
        if not canonical_path.exists() or not transfer_path.exists():
            print(
                "Error: --check requires existing provenance/canonical-source-manifest.json "
                "and provenance/transfer-manifest.json. Run without --check first.",
                file=sys.stderr,
            )
            return 1
        canonical_manifest = json.loads(canonical_path.read_text(encoding="utf-8"))
        transfer_manifest = json.loads(transfer_path.read_text(encoding="utf-8"))
    else:
        canonical_manifest = None
        transfer_manifest = None

    # Reconstruct the upstream source tree.
    upstream_dir = args.upstream_dir
    if upstream_dir is not None:
        upstream_dir = upstream_dir.resolve()
    else:
        import tempfile

        temp_dir = tempfile.TemporaryDirectory()
        upstream_dir = clone_upstream_commit(
            CANONICAL_RUP_REPO,
            args.commit,
            Path(temp_dir.name),
        )

    try:
        if canonical_manifest is None:
            canonical_manifest = build_canonical_source_manifest(
                ROOT, upstream_dir, canonical_commit=args.commit
            )
            transfer_manifest = build_transfer_manifest(ROOT, canonical_manifest)

        report = verify_transfer_manifest(ROOT, transfer_manifest, upstream_dir)

        if args.check:
            check_ok = report["valid"]
            if source_path.exists() and sha_path.exists():
                source_index = json.loads(source_path.read_text(encoding="utf-8"))
                canonical_rel = source_index.get("manifests", {}).get("canonical_source")
                if canonical_rel:
                    canonical_file = ROOT / canonical_rel
                    if canonical_file.exists():
                        actual_hash = hashlib.sha256(canonical_file.read_bytes()).hexdigest()
                        expected_hash = sha_path.read_text(encoding="utf-8").strip().split()[0]
                        if actual_hash != expected_hash:
                            print(
                                f"Error: source-manifest.sha256 does not match {canonical_rel} "
                                f"(expected {expected_hash}, got {actual_hash})",
                                file=sys.stderr,
                            )
                            check_ok = False
                        elif source_index.get("canonical_commit") != canonical_manifest.get("canonical_commit"):
                            print(
                                "Error: source-manifest.json canonical_commit does not match canonical-source-manifest.json",
                                file=sys.stderr,
                            )
                            check_ok = False
                    else:
                        print(f"Error: canonical source manifest not found: {canonical_file}", file=sys.stderr)
                        check_ok = False
                else:
                    print("Error: source-manifest.json is missing canonical_source reference", file=sys.stderr)
                    check_ok = False
            else:
                print("Warning: source-manifest.json or source-manifest.sha256 missing; skipping index consistency check", file=sys.stderr)

            status = "PASS" if check_ok else "FAIL"
            print(f"[{status}] Transfer verification: {report['passed']}/{report['checked']} passed")
            if not report["valid"]:
                for failure in report["failures"]:
                    print(f"  - {failure['source_path']} -> {failure['destination_path']}: {failure['reason']}", file=sys.stderr)
            return 0 if check_ok else 1

        # Write the manifests.
        _write_json(canonical_path, canonical_manifest)
        _write_json(transfer_path, transfer_manifest)

        source_index: Dict[str, Any] = {
            "generated_at": canonical_manifest["generated_at"],
            "canonical_repository": canonical_manifest["canonical_repository"],
            "canonical_commit": canonical_manifest["canonical_commit"],
            "canonical_protocol_version": canonical_manifest["canonical_protocol_version"],
            "manifests": {
                "canonical_source": str(canonical_path.relative_to(ROOT)),
                "transfer": str(transfer_path.relative_to(ROOT)),
            },
            "canonical_source_files": len(canonical_manifest["files"]),
            "transfers_recorded": len(transfer_manifest["transfers"]),
            "verification": report,
        }
        _write_json(source_path, source_index)

        canonical_sha = hashlib.sha256(
            canonical_path.read_bytes()
        ).hexdigest()
        sha_path.write_text(
            f"{canonical_sha}  canonical-source-manifest.json\n",
            encoding="utf-8",
        )

        print(f"Generated {canonical_path}")
        print(f"Generated {transfer_path}")
        print(f"Updated {source_path}")
        print(f"Updated {sha_path}")
        print(
            f"Transfer verification: {report['passed']}/{report['checked']} passed"
        )
        return 0
    finally:
        if args.upstream_dir is None:
            getattr(temp_dir, "cleanup", lambda: None)()


if __name__ == "__main__":
    sys.exit(main())
