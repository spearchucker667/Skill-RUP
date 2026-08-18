# Source Audit

## Execution

The source audit was executed at the beginning of the `Skill-RUP` port. The canonical repositories were inspected at their respective main branch commits:

- **RUP-Protocol Canonical Commit**: `c3d6f70375db15d53db2fba76d70b5b7c9cf98bb`
- **Skill-HQE Reference Commit**: `7f6f00be43bbf4442d231323a90d6460ecf68fcc`

## Inspection of `.reference/`

The local `.reference/` directory was inspected and hashed (hashes available in `provenance/source-manifest.json`).

### Findings

- **No Canonical RUP Sources Found**: The `.reference/` directory did **not** contain any files matching the canonical `rup-protocol.yaml` or `rup-schema.json`.
- **HQE Workbench Contamination**: The majority of the files in `.reference/` belong to `HQE_OR_HQE_WORKBENCH`, including `protocol/hqe-engineer.yaml`, `protocol/hqe-schema.json`, and various `mcp-server` assets.
- **Foreign/Unknown**: Standard boilerplate files (`.editorconfig`, etc.) were marked as `FOREIGN_OR_UNKNOWN`.

### Conclusion

Because `.reference/` contains only HQE material and foreign boilerplate, **none of its files were used as authoritative RUP inputs**. The RUP canonical sources must be fetched directly from the canonical repository commit `c3d6f70375db15d53db2fba76d70b5b7c9cf98bb`.
