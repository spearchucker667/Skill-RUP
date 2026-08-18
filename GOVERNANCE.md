# Project Governance

## Maintainership
The Skill-RUP project is currently maintained by the core contributors at the spearchucker667 organization.

## Decision Making
Decisions on architectural changes, protocol divergences, and releases are managed through GitHub Pull Requests and Issues.

## Canonical Source Authority
Changes to the underlying protocol behavior MUST be made upstream in the RUP-Protocol repository. This project serves as an implementation, and its `protocol/` directory serves as an exact synchronization of upstream releases. Pull requests attempting to modify the canonical RUP protocol or schema within this repository will be rejected in favor of upstream contribution.

## Security Decisions
Security patches are evaluated and managed according to our [Security Policy](SECURITY.md).

## Releases
Releases are cut when canonical RUP updates require a downstream sync, or when significant runtime capabilities are added. See [RELEASES.md](docs/RELEASES.md) for more details.
