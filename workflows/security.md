# Security Workflow

## Purpose
Address security gaps

## Canonical Rules & Process
Follow canonical RUP directives for this workflow.

## Raw Protocol Data
```yaml
id: ws_security
priority: P0
description: Address security gaps
components:
  secret_scanning:
    pre_commit: "# .pre-commit-config.yaml\nrepos:\n  - repo: https://github.com/gitleaks/gitleaks\n    rev: v8.18.0\n   \
      \ hooks:\n      - id: gitleaks\n"
    ci_workflow: "- name: Secret Scan\n  uses: gitleaks/gitleaks-action@v2\n"
  dependency_scanning:
    dependabot: "# .github/dependabot.yml\nversion: 2\nupdates:\n  - package-ecosystem: \"{ecosystem}\"\n    directory: \"\
      /\"\n    schedule:\n      interval: \"weekly\"\n    groups:\n      dependencies:\n        patterns:\n          - \"\
      *\"\n"
    renovate: "// renovate.json\n{\n  \"$schema\": \"https://docs.renovatebot.com/renovate-schema.json\",\n  \"extends\":\
      \ [\"config:recommended\"],\n  \"schedule\": [\"every weekend\"]\n}\n"
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
```

## Validation
Must comply with `rup-schema.json`.
