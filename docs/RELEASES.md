# Releases

Skill-RUP versions follow semantic versioning. The version typically matches the canonical RUP Protocol version being packaged (e.g. `v3.0.0`), with an optional suffix for downstream patches.

## Release Process
1. Verify the CI pipeline and test suite pass successfully.
2. Run `scripts/package_skill.py` to regenerate the `dist/` archive.
3. Update `CHANGELOG.md`.
4. Trigger the GitHub Release Action via `.github/workflows/release-package.yml`.

## Post-Release Verification
- Download the generated zip artifact from the GitHub Release page.
- Compare the SHA-256 hash against the generated `manifest.json`.

## Hard Invariant
The source tree used for release MUST be the exact source tree represented by the manifest and package.
