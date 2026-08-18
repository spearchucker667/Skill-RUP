"""
Source authority verification and canonical RUP lineage validator.
"""
from pathlib import Path
from typing import Dict, Any, Optional
import hashlib
from .security import safe_load_yaml

CANONICAL_RUP_REPO = "https://github.com/spearchucker667/RUP-Protocol"
CANONICAL_RUP_COMMIT = "c3d6f70375db15d53db2fba76d70b5b7c9cf98bb"
CANONICAL_PROTOCOL_VERSION = "3.0.0"

SOURCE_AUTHORITY = {
    "canonical_repo": CANONICAL_RUP_REPO,
    "canonical_commit": CANONICAL_RUP_COMMIT,
    "canonical_version": CANONICAL_PROTOCOL_VERSION,
}


class SourceAuthority:
    def __init__(self, skill_root: Path):
        self.skill_root = skill_root

    def get_authority_declaration(self) -> Dict[str, Any]:
        """Return the canonical authority metadata."""
        return {
            "canonical_repository": CANONICAL_RUP_REPO,
            "canonical_commit": CANONICAL_RUP_COMMIT,
            "protocol_version": CANONICAL_PROTOCOL_VERSION,
            "license": "CC0-1.0",
            "authority_hierarchy": [
                "protocol/rup-protocol.yaml (Canonical Behavioral Specification)",
                "protocol/rup-schema.json (Canonical Validation Contract)",
                "SKILL.md (Compact Operational Projection & Workflow Router)",
                "runtime/ (Deterministic Execution Engine)"
            ]
        }

    def verify_protocol_authority(self, proto_path: Optional[Path] = None) -> Dict[str, Any]:
        """Verify the local protocol file against canonical requirements."""
        if proto_path is None:
            proto_path = self.skill_root / "protocol" / "rup-protocol.yaml"

        if not proto_path.exists():
            return {
                "verified": False,
                "error": f"Protocol file missing: {proto_path}"
            }

        try:
            data = safe_load_yaml(proto_path)
            proto_ver = str(data.get("protocol_version", ""))
            schema_ver = str(data.get("schema_version", ""))

            is_valid = (proto_ver == CANONICAL_PROTOCOL_VERSION and schema_ver == CANONICAL_PROTOCOL_VERSION)
            return {
                "verified": is_valid,
                "protocol_version": proto_ver,
                "schema_version": schema_ver,
                "canonical_commit": CANONICAL_RUP_COMMIT,
                "protocol_path": str(proto_path),
            }
        except Exception as e:
            return {
                "verified": False,
                "error": str(e)
            }

