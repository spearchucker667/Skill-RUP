# 3 Execution Workflow

## Purpose
No description provided.

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
agent: execution_agent
id: phase_3_execution
name: Implementation
output_template: '# CHANGES


  ## Summary

  - **Files Changed**: {files_changed}

  - **Files Created**: {files_created}

  - **Lines Added**: {lines_added}

  - **Lines Removed**: {lines_removed}


  ## Changes by Category


  ### Bug Fixes

  {bug_fixes}


  ### Tests

  {tests}


  ### CI/CD

  {ci_cd}


  ### Security

  {security}


  ### Documentation

  {documentation}


  ## Commits

  {commits}


  ## Patches

  {patches}

  '
timeout_minutes: 45
workstreams:
  bug_fixes:
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
    description: Fix identified bugs with regression tests
    id: ws_bugs
    priority: P0
    process:
    - details: Highest severity, lowest complexity
      step: Select bug from backlog
    - details: Test must reproduce the bug
      step: Write failing test
    - details: Prefer targeted over broad changes
      step: Implement minimal fix
    - details: Run 3x to check for flakiness
      step: Verify test passes
    - details: Add to changelog, update affected docs
      step: Update documentation
  ci_cd:
    description: Add or fix CI/CD workflows
    id: ws_ci
    platforms:
      circleci:
        basic: "version: 2.1\njobs:\n  test:\n    docker:\n      - image: # Base image\n\
          \    steps:\n      - checkout\n      - run: # Install\n      - run: # Test\n\
          workflows:\n  main:\n    jobs:\n      - test\n"
      github_actions:
        basic_ci: "name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on:\
          \ ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      -\
          \ name: Setup\n        # Language-specific setup\n      - name: Install\n\
          \        run: # Install command\n      - name: Lint\n        run: # Lint\
          \ command\n      - name: Test\n        run: # Test command\n"
        security: "name: Security\non:\n  push:\n    branches: [main]\n  pull_request:\n\
          \  schedule:\n    - cron: '0 0 * * 0'\njobs:\n  codeql:\n    runs-on: ubuntu-latest\n\
          \    permissions:\n      security-events: write\n    steps:\n      - uses:\
          \ actions/checkout@v4\n      - uses: github/codeql-action/init@v3\n    \
          \  - uses: github/codeql-action/autobuild@v3\n      - uses: github/codeql-action/analyze@v3\n"
      gitlab_ci:
        basic: "stages:\n  - test\n  - security\n\ntest:\n  stage: test\n  script:\n\
          \    - # Install\n    - # Lint\n    - # Test\n\nsecurity:\n  stage: security\n\
          \  script:\n    - # Security scan\n"
    priority: P0
  containerization:
    best_practices:
    - Use multi-stage builds
    - Use non-root user
    - Use distroless/minimal base images
    - Pin dependency versions
    - Add health checks
    - Minimize layers
    - Use .dockerignore
    compose_template: "version: '3.8'\nservices:\n  app:\n    build: .\n    ports:\n\
      \      - \"{port}:{port}\"\n    environment:\n      - NODE_ENV=production\n\
      \    healthcheck:\n      test: {health_check}\n      interval: 30s\n      timeout:\
      \ 10s\n      retries: 3\n"
    description: Add containerization best practices
    dockerfile_template: "# syntax=docker/dockerfile:1\n\n# Build stage\nFROM {base_image}\
      \ AS builder\nWORKDIR /app\nCOPY {lockfile} .\nRUN {install_command}\nCOPY .\
      \ .\nRUN {build_command}\n\n# Runtime stage\nFROM {runtime_image}\nRUN adduser\
      \ --disabled-password --gecos \"\" appuser\nUSER appuser\nWORKDIR /app\nCOPY\
      \ --from=builder /app/{artifact} .\nEXPOSE {port}\nHEALTHCHECK --interval=30s\
      \ --timeout=3s \\\n  CMD {health_check_command}\nCMD [\"{entrypoint}\"]\n"
    id: ws_containers
    priority: P2
  documentation:
    description: Improve documentation
    id: ws_docs
    priority: P1
    templates:
      codeowners: '# CODEOWNERS

        # Default owners

        * @{default_team}


        # Specific paths

        /src/ @{dev_team}

        /docs/ @{docs_team}

        /.github/ @{devops_team}

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
  governance:
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
    branch_protection:
      main:
        allow_deletions: false
        allow_force_pushes: false
        dismiss_stale_reviews: true
        require_branches_up_to_date: true
        require_code_owner_reviews: true
        require_status_checks:
        - test
        - lint
        - security
        required_reviews: 1
        restrict_pushes: true
    description: Add governance and automation
    id: ws_governance
    priority: P1
  observability:
    description: Add logging, metrics, tracing
    id: ws_observability
    logging:
      example: "{\n  \"timestamp\": \"2025-01-18T12:00:00Z\",\n  \"level\": \"info\"\
        ,\n  \"message\": \"Request processed\",\n  \"service\": \"api\",\n  \"trace_id\"\
        : \"abc123\",\n  \"duration_ms\": 42\n}\n"
      fields:
      - timestamp
      - level
      - message
      - service
      - trace_id
      - span_id
      format: JSON structured logging
    metrics:
      standard:
      - request_count
      - request_duration_seconds
      - error_count
      - active_connections
    priority: P2
    tracing:
      propagation: W3C Trace Context
      standard: OpenTelemetry
  security:
    components:
      dependency_scanning:
        dependabot: "# .github/dependabot.yml\nversion: 2\nupdates:\n  - package-ecosystem:\
          \ \"{ecosystem}\"\n    directory: \"/\"\n    schedule:\n      interval:\
          \ \"weekly\"\n    groups:\n      dependencies:\n        patterns:\n    \
          \      - \"*\"\n"
        renovate: "// renovate.json\n{\n  \"$schema\": \"https://docs.renovatebot.com/renovate-schema.json\"\
          ,\n  \"extends\": [\"config:recommended\"],\n  \"schedule\": [\"every weekend\"\
          ]\n}\n"
      sbom_generation:
        github_action: "- name: Generate SBOM\n  uses: anchore/sbom-action@v0\n  with:\n\
          \    format: spdx-json\n    output-file: sbom.spdx.json\n"
      secret_scanning:
        ci_workflow: "- name: Secret Scan\n  uses: gitleaks/gitleaks-action@v2\n"
        pre_commit: "# .pre-commit-config.yaml\nrepos:\n  - repo: https://github.com/gitleaks/gitleaks\n\
          \    rev: v8.18.0\n    hooks:\n      - id: gitleaks\n"
      security_md_template: "# Security Policy\n\n## Supported Versions\n| Version\
        \ | Supported |\n|---------|-----------|\n| {version} | \u2705 |\n\n## Reporting\
        \ a Vulnerability\n\n**Do NOT report via public GitHub issues.**\n\nEmail:\
        \ {security_email}\n\nResponse time: 48 hours\nDisclosure policy: 90-day coordinated\
        \ disclosure\n"
    description: Address security gaps
    id: ws_security
    priority: P0
  tests:
    coverage_targets:
      e2e: Critical paths
      integration: 60%
      unit: 80%
    description: Add missing tests for critical paths
    guidelines:
    - Focus on business logic and edge cases
    - Follow existing test conventions
    - 'Use AAA pattern: Arrange, Act, Assert'
    - Mock external dependencies
    - Aim for determinism (no flaky tests)
    id: ws_tests
    naming_conventions:
      go: Test{Function}_{Scenario}
      javascript: describe/it pattern
      python: test_{function}_{scenario}_{expected}
      rust: test_{function}_{scenario}
    priority: P0

```

## Validation
Must comply with `rup-schema.json`.
