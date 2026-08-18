# Source Audit Raw Copies

This directory previously contained a nested Git checkout of the canonical RUP Protocol repository.
That checkout was recorded as a gitlink without a matching `.gitmodules` declaration, which created a malformed submodule state and broke portable clones.

The nested repository has been removed from the index and working tree. The canonical source remains authoritative at:

- **Repository**: `https://github.com/spearchucker667/RUP-Protocol`
- **Protocol version**: `3.0.0`
- **Canonical commit**: `c3d6f70375db15d53db2fba76d70b5b7c9cf98bb`

Local copies of canonical files are intentionally **not** vendored here. Use the provenance metadata under `provenance/` for lineage tracking.
