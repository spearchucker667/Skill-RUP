# Discovery Rules - Canonical Reference

This document outlines the canonical rules and heuristics for the Discovery phase of RUP Protocol v3.0.0.

## Phase 1: Discovery

### 1.1 Repository Inventory

**Purpose**: Comprehensive cataloging of repository contents and metadata.

**Rules**:
- Scan all files in the repository root and subdirectories
- Exclude `.git/`, `.venv/`, `node_modules/`, and other standard ignore patterns
- Classify files by:
  - Language (by extension and content analysis)
  - Type (source, test, config, doc, build artifact)
  - Size (track bytes for each file)
- Count lines of code (LOC) per language
- Identify lockfiles (package-lock.json, yarn.lock, poetry.lock, etc.)
- Detect monorepo structures (pnpm-workspace, lerna, nx, turbo, cargo workspaces)

**Required Outputs**:
- `repo_metadata`: name, primary_language, repo_type, loc, file_count, contributors, last_commit, open_issues, license
- `languages`: array of {name, percentage, lockfile_present}
- `file_inventory`: structured list of all files with metadata

### 1.2 Tooling Detection

**Purpose**: Identify all development, testing, linting, and build tools.

**Rules**:
- **Python**: pytest, unittest, ruff, flake8, black, mypy, poetry, pipenv, flit, hatch
- **JavaScript/TypeScript**: jest, vitest, mocha, eslint (including flat config `eslint.config.*`), prettier, tsc, npm, yarn, pnpm
- **Go**: go test, golangci-lint
- **Rust**: cargo test, clippy
- **CI/CD**: GitHub Actions, GitLab CI, CircleCI
- **Containers**: Dockerfile, docker-compose
- **IaC**: Terraform, Pulumi

**Required Outputs**:
- `tooling`: structured object with detected tools per category

### 1.3 Quality Assessment

**Purpose**: Evaluate code quality through static analysis.

**Rules**:
- Analyze complexity metrics where possible
- Detect code duplication
- Identify lint violations (if linter configs exist)
- Assess test coverage (if coverage reports exist)

**Required Outputs**:
- `quality_metrics`: complexity_score, duplication_score, lint_violations, test_coverage

### 1.4 Security Assessment

**Purpose**: Identify security risks and vulnerabilities.

**Rules**:
- Scan for secrets (API keys, tokens, private keys, passwords, bearer tokens)
- Check for unsafe patterns (eval, exec, shell=True, etc.)
- Verify SECURITY.md existence and content
- Check for SBOM (Software Bill of Materials)
- Review license compliance
- Scan dependencies for known vulnerabilities

**Required Outputs**:
- `security_findings`: secrets_found, unsafe_patterns, dependency_vulnerabilities, security_policy_present, sbom_present, license_compliance

### 1.5 Documentation Assessment

**Purpose**: Evaluate documentation completeness.

**Rules**:
- Check for README.md (root and per-package)
- Verify API documentation existence
- Check for CONTRIBUTING.md
- Check for CODE_OF_CONDUCT.md
- Review ADR (Architecture Decision Record) directory

**Required Outputs**:
- `documentation`: readme_present, api_docs_present, contributing_present, code_of_conduct_present, adrs_present

### 1.6 Governance Assessment

**Purpose**: Evaluate repository governance structures.

**Rules**:
- Check CODEOWNERS file
- Verify issue templates exist
- Verify PR templates exist
- Check branch protection configuration
- Review release automation setup

**Required Outputs**:
- `governance`: codeowners_present, issue_templates, pr_templates, branch_protection, release_automation

### 1.7 Gap Analysis & Scoring

**Purpose**: Synthesize findings and produce actionable gaps.

**Rules**:
- Score technical debt from 0-100 (higher = worse)
- Score production readiness from 0-100 (higher = better)
- Assign overall risk level (low, medium, high, critical)
- Generate prioritized gaps with:
  - id (unique identifier)
  - category (tests, security, docs, ci, governance, etc.)
  - severity (critical, high, medium, low)
  - title (descriptive)
  - description (detailed)
  - impact (effect on the codebase)
  - suggested_fix (remediation recommendation)
  - effort_estimate (small, medium, large)
  - files_affected (list of relevant files)

**Required Outputs**:
- `risk_assessment`: overall_risk, technical_debt_score, production_readiness_score, risk_factors
- `gaps`: array of gap objects sorted by severity then effort
