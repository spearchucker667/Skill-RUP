# 3 Implementation Workflow

## Purpose
Implementation

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
id: phase_3_execution
name: Implementation
agent: execution_agent
timeout_minutes: 45
workstreams:
  bug_fixes:
    id: ws_bugs
    priority: P0
    description: Fix identified bugs with regression tests
    process:
    - step: Select bug from backlog
      details: Highest severity, lowest complexity
    - step: Write failing test
      details: Test must reproduce the bug
    - step: Implement minimal fix
      details: Prefer targeted over broad changes
    - step: Verify test passes
      details: Run 3x to check for flakiness
    - step: Update documentation
      details: Add to changelog, update affected docs
    bug_report_template: '## Bug: {title}


      **Severity**: {severity}

      **File**: {file}:{line}

      **Root Cause**: {root_cause}


      ### Reproduction

      ```{language}

      {reproduction_code}

      ```


      ### Fix

      {fix_description}


      ### Regression Test

      {test_name} in {test_file}

      '
  tests:
    id: ws_tests
    priority: P0
    description: Add missing tests for critical paths
    guidelines:
    - Focus on business logic and edge cases
    - Follow existing test conventions
    - 'Use AAA pattern: Arrange, Act, Assert'
    - Mock external dependencies
    - Aim for determinism (no flaky tests)
    coverage_targets:
      unit: 80%
      integration: 60%
      e2e: Critical paths
    naming_conventions:
      python: test_{function}_{scenario}_{expected}
      javascript: describe/it pattern
      go: Test{Function}_{Scenario}
      rust: test_{function}_{scenario}
  ci_cd:
    id: ws_ci
    priority: P0
    description: Add or fix CI/CD workflows
    platforms:
      github_actions:
        basic_ci: "name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses:\
          \ actions/checkout@v4\n      - name: Setup\n        # Language-specific setup\n      - name: Install\n        run:\
          \ # Install command\n      - name: Lint\n        run: # Lint command\n      - name: Test\n        run: # Test command\n"
        security: "name: Security\non:\n  push:\n    branches: [main]\n  pull_request:\n  schedule:\n    - cron: '0 0 * *\
          \ 0'\njobs:\n  codeql:\n    runs-on: ubuntu-latest\n    permissions:\n      security-events: write\n    steps:\n\
          \      - uses: actions/checkout@v4\n      - uses: github/codeql-action/init@v3\n      - uses: github/codeql-action/autobuild@v3\n\
          \      - uses: github/codeql-action/analyze@v3\n"
      gitlab_ci:
        basic: "stages:\n  - test\n  - security\n\ntest:\n  stage: test\n  script:\n    - # Install\n    - # Lint\n    - #\
          \ Test\n\nsecurity:\n  stage: security\n  script:\n    - # Security scan\n"
      circleci:
        basic: "version: 2.1\njobs:\n  test:\n    docker:\n      - image: # Base image\n    steps:\n      - checkout\n   \
          \   - run: # Install\n      - run: # Test\nworkflows:\n  main:\n    jobs:\n      - test\n"
  security:
    id: ws_security
    priority: P0
    description: Address security gaps
    components:
      secret_scanning:
        pre_commit: "# .pre-commit-config.yaml\nrepos:\n  - repo: https://github.com/gitleaks/gitleaks\n    rev: v8.18.0\n\
          \    hooks:\n      - id: gitleaks\n"
        ci_workflow: "- name: Secret Scan\n  uses: gitleaks/gitleaks-action@v2\n"
      dependency_scanning:
        dependabot: "# .github/dependabot.yml\nversion: 2\nupdates:\n  - package-ecosystem: \"{ecosystem}\"\n    directory:\
          \ \"/\"\n    schedule:\n      interval: \"weekly\"\n    groups:\n      dependencies:\n        patterns:\n      \
          \    - \"*\"\n"
        renovate: "// renovate.json\n{\n  \"$schema\": \"https://docs.renovatebot.com/renovate-schema.json\",\n  \"extends\"\
          : [\"config:recommended\"],\n  \"schedule\": [\"every weekend\"]\n}\n"
      sbom_generation:
        github_action: "- name: Generate SBOM\n  uses: anchore/sbom-action@v0\n  with:\n    format: spdx-json\n    output-file:\
          \ sbom.spdx.json\n"
      security_md_template: '# Security Policy


        ## Supported Versions

        | Version | Supported |

        |---------|-----------|

        | {version} | ✅ |


        ## Reporting a Vulnerability


        **Do NOT report via public GitHub issues.**


        Email: {security_email}


        Response time: 48 hours

        Disclosure policy: 90-day coordinated disclosure

        '
  documentation:
    id: ws_docs
    priority: P1
    description: Improve documentation
    templates:
      readme: '# {Project Name}


        {badges}


        {description}


        ## Features

        - Feature 1

        - Feature 2


        ## Installation

        ```bash

        {install_command}

        ```


        ## Usage

        ```{language}

        {usage_example}

        ```


        ## Configuration

        | Variable | Description | Default |

        |----------|-------------|---------|

        {config_table}


        ## Development

        ```bash

        {dev_setup}

        ```


        ## Testing

        ```bash

        {test_command}

        ```


        ## Contributing

        See [CONTRIBUTING.md](CONTRIBUTING.md)


        ## License

        {license}

        '
      contributing: '# Contributing


        ## Development Setup

        1. Fork and clone

        2. Install dependencies: `{install_command}`

        3. Create branch: `git checkout -b feature/name`


        ## Workflow

        1. Make changes

        2. Run tests: `{test_command}`

        3. Run lint: `{lint_command}`

        4. Commit (conventional commits)

        5. Push and create PR


        ## Code Standards

        - {standard_1}

        - {standard_2}

        '
      codeowners: '# CODEOWNERS

        # Default owners

        * @{default_team}


        # Specific paths

        /src/ @{dev_team}

        /docs/ @{docs_team}

        /.github/ @{devops_team}

        '
      issue_template_bug: '---

        name: Bug Report

        about: Report a bug

        labels: bug

        ---


        ## Description


        ## Steps to Reproduce

        1.


        ## Expected Behavior


        ## Actual Behavior


        ## Environment

        - OS:

        - Version:

        '
      issue_template_feature: '---

        name: Feature Request

        about: Suggest a feature

        labels: enhancement

        ---


        ## Problem


        ## Proposed Solution


        ## Alternatives Considered

        '
      pr_template: '## Description


        ## Type of Change

        - [ ] Bug fix

        - [ ] New feature

        - [ ] Breaking change

        - [ ] Documentation


        ## Checklist

        - [ ] Tests pass

        - [ ] Linting passes

        - [ ] Documentation updated

        - [ ] Conventional commit format

        '
  governance:
    id: ws_governance
    priority: P1
    description: Add governance and automation
    branch_protection:
      main:
        required_reviews: 1
        dismiss_stale_reviews: true
        require_code_owner_reviews: true
        require_status_checks:
        - test
        - lint
        - security
        require_branches_up_to_date: true
        restrict_pushes: true
        allow_force_pushes: false
        allow_deletions: false
    adr_template: '# ADR {number}: {title}


      ## Status

      {Proposed|Accepted|Deprecated|Superseded}


      ## Context

      {What is the issue?}


      ## Decision

      {What is the change?}


      ## Consequences

      {What becomes easier/harder?}


      ## Alternatives Considered

      {What else was considered?}

      '
  containerization:
    id: ws_containers
    priority: P2
    description: Add containerization best practices
    dockerfile_template: "# syntax=docker/dockerfile:1\n\n# Build stage\nFROM {base_image} AS builder\nWORKDIR /app\nCOPY\
      \ {lockfile} .\nRUN {install_command}\nCOPY . .\nRUN {build_command}\n\n# Runtime stage\nFROM {runtime_image}\nRUN adduser\
      \ --disabled-password --gecos \"\" appuser\nUSER appuser\nWORKDIR /app\nCOPY --from=builder /app/{artifact} .\nEXPOSE\
      \ {port}\nHEALTHCHECK --interval=30s --timeout=3s \\\n  CMD {health_check_command}\nCMD [\"{entrypoint}\"]\n"
    best_practices:
    - Use multi-stage builds
    - Use non-root user
    - Use distroless/minimal base images
    - Pin dependency versions
    - Add health checks
    - Minimize layers
    - Use .dockerignore
    compose_template: "version: '3.8'\nservices:\n  app:\n    build: .\n    ports:\n      - \"{port}:{port}\"\n    environment:\n\
      \      - NODE_ENV=production\n    healthcheck:\n      test: {health_check}\n      interval: 30s\n      timeout: 10s\n\
      \      retries: 3\n"
  observability:
    id: ws_observability
    priority: P2
    description: Add logging, metrics, tracing
    logging:
      format: JSON structured logging
      fields:
      - timestamp
      - level
      - message
      - service
      - trace_id
      - span_id
      example: "{\n  \"timestamp\": \"2025-01-18T12:00:00Z\",\n  \"level\": \"info\",\n  \"message\": \"Request processed\"\
        ,\n  \"service\": \"api\",\n  \"trace_id\": \"abc123\",\n  \"duration_ms\": 42\n}\n"
    metrics:
      standard:
      - request_count
      - request_duration_seconds
      - error_count
      - active_connections
    tracing:
      standard: OpenTelemetry
      propagation: W3C Trace Context
```

## Validation
Must comply with `rup-schema.json`.
