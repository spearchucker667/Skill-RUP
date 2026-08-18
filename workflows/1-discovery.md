# 1 Discovery & analysis Workflow

## Purpose
Discovery & Analysis

## Canonical Rules & Process
1. **Repository Inventory**: Identify languages, frameworks, package managers Detect repo type (library, app, service, CLI, monorepo) Count files, LOC, contributors Analyze git history (commit frequency, last activity) Detect monorepo structure if applicable
1. **Tooling Detection**: Identify test framework and test locations Detect linter and formatter configuration Find build tools and scripts Detect CI platform and workflows Identify containerization (Docker, K8s) Detect IaC tools (Terraform, Pulumi)
1. **Quality Assessment**: Measure test coverage (if tooling available) Count lint violations Assess code complexity Check for code duplication Evaluate technical debt
1. **Security Assessment**: Scan for exposed secrets Check dependency vulnerabilities Identify unsafe patterns Verify SECURITY.md presence Check for SBOM Assess license compliance
1. **Documentation Assessment**: Evaluate README completeness Check API documentation coverage Verify CONTRIBUTING.md, CODE_OF_CONDUCT.md Check for ADRs Assess example/tutorial coverage
1. **Governance Assessment**: Check CODEOWNERS presence Evaluate issue/PR templates Check branch protection rules Assess CI/CD maturity Check for release automation
1. **Gap Analysis**: Compile critical gaps with severity Calculate overall risk score Identify quick wins vs complex fixes Score production readiness (0-100) Score technical debt (0-100)

## Raw Protocol Data
```yaml
id: phase_1_discovery
name: Discovery & Analysis
agent: discovery_agent
timeout_minutes: 10
steps:
- id: '1.1'
  name: Repository Inventory
  actions:
  - Identify languages, frameworks, package managers
  - Detect repo type (library, app, service, CLI, monorepo)
  - Count files, LOC, contributors
  - Analyze git history (commit frequency, last activity)
  - Detect monorepo structure if applicable
- id: '1.2'
  name: Tooling Detection
  actions:
  - Identify test framework and test locations
  - Detect linter and formatter configuration
  - Find build tools and scripts
  - Detect CI platform and workflows
  - Identify containerization (Docker, K8s)
  - Detect IaC tools (Terraform, Pulumi)
- id: '1.3'
  name: Quality Assessment
  actions:
  - Measure test coverage (if tooling available)
  - Count lint violations
  - Assess code complexity
  - Check for code duplication
  - Evaluate technical debt
- id: '1.4'
  name: Security Assessment
  actions:
  - Scan for exposed secrets
  - Check dependency vulnerabilities
  - Identify unsafe patterns
  - Verify SECURITY.md presence
  - Check for SBOM
  - Assess license compliance
- id: '1.5'
  name: Documentation Assessment
  actions:
  - Evaluate README completeness
  - Check API documentation coverage
  - Verify CONTRIBUTING.md, CODE_OF_CONDUCT.md
  - Check for ADRs
  - Assess example/tutorial coverage
- id: '1.6'
  name: Governance Assessment
  actions:
  - Check CODEOWNERS presence
  - Evaluate issue/PR templates
  - Check branch protection rules
  - Assess CI/CD maturity
  - Check for release automation
- id: '1.7'
  name: Gap Analysis
  actions:
  - Compile critical gaps with severity
  - Calculate overall risk score
  - Identify quick wins vs complex fixes
  - Score production readiness (0-100)
  - Score technical debt (0-100)
```

## Validation
Must comply with `rup-schema.json`.
