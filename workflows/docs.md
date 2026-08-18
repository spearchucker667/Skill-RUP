# Docs Workflow

## Purpose
Improve documentation

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
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

```

## Validation
Must comply with `rup-schema.json`.
