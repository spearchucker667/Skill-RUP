# 1 Discovery Workflow

## Purpose
No description provided.

## Canonical Rules & Process
1. **Repository Inventory**: 
1. **Tooling Detection**: 
1. **Quality Assessment**: 
1. **Security Assessment**: 
1. **Documentation Assessment**: 
1. **Governance Assessment**: 
1. **Gap Analysis**: 

## Raw Protocol Data
```yaml
agent: discovery_agent
id: phase_1_discovery
name: Discovery & Analysis
output_template: '# DISCOVERY REPORT


  ## Executive Summary

  - **Repository**: {repo_name}

  - **Type**: {repo_type}

  - **Primary Language**: {primary_language}

  - **Production Readiness**: {readiness_score}/100

  - **Technical Debt**: {debt_score}/100

  - **Overall Risk**: {risk_level}


  ## Repository Metadata

  | Property | Value |

  |----------|-------|

  | Lines of Code | {loc:,} |

  | Files | {file_count} |

  | Contributors | {contributors} |

  | Last Commit | {last_commit} |

  | Open Issues | {open_issues} |

  | License | {license} |


  ## Languages & Tooling

  | Language | % | Package Manager | Test Framework | Linter |

  |----------|---|-----------------|----------------|--------|

  {language_table}


  ## Monorepo Structure

  {monorepo_section}


  ## Critical Gaps

  | ID | Gap | Severity | Impact | Suggested Fix | Effort |

  |----|-----|----------|--------|---------------|--------|

  {gaps_table}


  ## Risk Assessment

  | Risk Factor | Severity | Mitigation |

  |-------------|----------|------------|

  {risk_table}

  '
steps:
- actions:
  - Identify languages, frameworks, package managers
  - Detect repo type (library, app, service, CLI, monorepo)
  - Count files, LOC, contributors
  - Analyze git history (commit frequency, last activity)
  - Detect monorepo structure if applicable
  id: '1.1'
  name: Repository Inventory
- actions:
  - Identify test framework and test locations
  - Detect linter and formatter configuration
  - Find build tools and scripts
  - Detect CI platform and workflows
  - Identify containerization (Docker, K8s)
  - Detect IaC tools (Terraform, Pulumi)
  id: '1.2'
  name: Tooling Detection
- actions:
  - Measure test coverage (if tooling available)
  - Count lint violations
  - Assess code complexity
  - Check for code duplication
  - Evaluate technical debt
  id: '1.3'
  name: Quality Assessment
- actions:
  - Scan for exposed secrets
  - Check dependency vulnerabilities
  - Identify unsafe patterns
  - Verify SECURITY.md presence
  - Check for SBOM
  - Assess license compliance
  id: '1.4'
  name: Security Assessment
- actions:
  - Evaluate README completeness
  - Check API documentation coverage
  - Verify CONTRIBUTING.md, CODE_OF_CONDUCT.md
  - Check for ADRs
  - Assess example/tutorial coverage
  id: '1.5'
  name: Documentation Assessment
- actions:
  - Check CODEOWNERS presence
  - Evaluate issue/PR templates
  - Check branch protection rules
  - Assess CI/CD maturity
  - Check for release automation
  id: '1.6'
  name: Governance Assessment
- actions:
  - Compile critical gaps with severity
  - Calculate overall risk score
  - Identify quick wins vs complex fixes
  - Score production readiness (0-100)
  - Score technical debt (0-100)
  id: '1.7'
  name: Gap Analysis
timeout_minutes: 10

```

## Validation
Must comply with `rup-schema.json`.
