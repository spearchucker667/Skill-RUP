# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- Complete RUP Protocol v3.0.0 synchronization.
- Agent workflow projections in `workflows/`.
- Strict schema extraction for state artifacts.
- Deterministic Python 3.11+ runtime for Discovery, Planning, Execution, Verification, and Reporting.
- Robust security jailing and prompt-injection detection.
- Deep capability mapping and validation tracking.
- Test suites covering integration and portability.

### Changed
- Refactored `SKILL.md` to properly route sub-workflows and enforce schema validation.
- Restructured `runtime/` to strictly return typed outputs and adhere to Schema Draft 2020-12.
