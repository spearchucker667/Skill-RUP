# Ci Cd Workflow

## Purpose
Add or fix CI/CD workflows

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
description: Add or fix CI/CD workflows
id: ws_ci
platforms:
  circleci:
    basic: "version: 2.1\njobs:\n  test:\n    docker:\n      - image: # Base image\n\
      \    steps:\n      - checkout\n      - run: # Install\n      - run: # Test\n\
      workflows:\n  main:\n    jobs:\n      - test\n"
  github_actions:
    basic_ci: "name: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n\
      \    steps:\n      - uses: actions/checkout@v4\n      - name: Setup\n      \
      \  # Language-specific setup\n      - name: Install\n        run: # Install\
      \ command\n      - name: Lint\n        run: # Lint command\n      - name: Test\n\
      \        run: # Test command\n"
    security: "name: Security\non:\n  push:\n    branches: [main]\n  pull_request:\n\
      \  schedule:\n    - cron: '0 0 * * 0'\njobs:\n  codeql:\n    runs-on: ubuntu-latest\n\
      \    permissions:\n      security-events: write\n    steps:\n      - uses: actions/checkout@v4\n\
      \      - uses: github/codeql-action/init@v3\n      - uses: github/codeql-action/autobuild@v3\n\
      \      - uses: github/codeql-action/analyze@v3\n"
  gitlab_ci:
    basic: "stages:\n  - test\n  - security\n\ntest:\n  stage: test\n  script:\n \
      \   - # Install\n    - # Lint\n    - # Test\n\nsecurity:\n  stage: security\n\
      \  script:\n    - # Security scan\n"
priority: P0

```

## Validation
Must comply with `rup-schema.json`.
