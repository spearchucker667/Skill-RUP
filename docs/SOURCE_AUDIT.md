# Source Audit

## Execution

The source audit was executed at the beginning of the `Skill-RUP` port. The canonical repository was inspected at its main branch commit:

- **RUP-Protocol Canonical Commit**: `c3d6f70375db15d53db2fba76d70b5b7c9cf98bb`

## Provenance Manifests

After the C-02 remediation, provenance is represented by two machine-readable
files in `provenance/`:

1. **`provenance/canonical-source-manifest.json`** — enumerates the pinned
   upstream RUP-Protocol source tree. Every upstream blob is recorded with its
   path, Git blob SHA, SHA-256, size, and the Skill-RUP destination path it maps
   to (if any).
2. **`provenance/transfer-manifest.json`** — records how each upstream source
   was transferred into Skill-RUP. Fields include:
   - `transfer_type`: `exact_copy`, `derived`, `translated`, or `omitted`
   - `transformation_tool`: the tool or process that produced the destination
   - `destination_sha256` and `destination_git_blob_sha`
   - `parity_tests`: tests that demonstrate the transfer is faithful
   - `rationale`: why the file was copied, adapted, or omitted

The top-level index `provenance/source-manifest.json` points to the two
manifests above and includes the result of the last transfer verification.

## Inspection of `.reference/`

The local `.reference/` directory was inspected and hashed during the original
audit (hashes are no longer used as the authoritative provenance record).

### Findings

- **No Canonical RUP Sources Found**: The `.reference/` directory did **not**
  contain any files matching the canonical `rup-protocol.yaml` or
  `rup-schema.json`.
- **HQE Workbench Contamination**: The majority of the files in `.reference/`
  belong to `HQE_OR_HQE_WORKBENCH`, including `protocol/hqe-engineer.yaml`,
  `protocol/hqe-schema.json`, and various `mcp-server` assets.
- **Foreign/Unknown**: Standard boilerplate files (`.editorconfig`, etc.) were
  marked as `FOREIGN_OR_UNKNOWN`.

### Conclusion

Because `.reference/` contains only HQE material and foreign boilerplate,
**none of its files were used as authoritative RUP inputs**. The RUP canonical
sources are fetched directly from the canonical repository commit
`c3d6f70375db15d53db2fba76d70b5b7c9cf98bb` and tracked through the manifests in
`provenance/`.

## Reconstructing and Verifying the Transfer

CI can reconstruct and verify the transfer from the pinned commit:

```bash
python scripts/audit_sources.py --check
```

The script clones the canonical repository at the pinned commit, rebuilds the
upstream source tree, and verifies that every recorded destination hash matches
the upstream blob. A failing verification returns a non-zero exit code and lists
the mismatched files.
