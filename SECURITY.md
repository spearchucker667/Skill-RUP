# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 3.0.x   | :white_check_mark: |
| < 3.0   | :x:                |

## Reporting a Vulnerability

Please report security issues privately. **Do not create public GitHub issues for security vulnerabilities.**

To report a vulnerability, please email spearchucker667@users.noreply.github.com or use GitHub's private vulnerability reporting feature if available for this repository.

### What to Include
* Description of the vulnerability.
* Steps to reproduce (including Skill-RUP version, OS, agent platform, and target repo characteristics).
* Potential impact.

### Scope
We are explicitly interested in vulnerabilities that compromise the host environment or agent boundary:
- Path traversal and symlink escape vulnerabilities.
- Arbitrary command execution or shell injection in the `runtime/` components.
- Prompt-injection boundary failures that lead to unsafe execution.
- Malicious repository content handling (e.g. archive traversal, YAML bombs).
- Secret leakage in logs or generated artifacts.
- State and provenance manipulation.
- Dependency confusion or hallucination in the workflow or execution engine.
- Unsafe Git operations.

## Coordination
We will acknowledge your report within 48 hours and work with you to understand and resolve the issue. We aim to coordinate a fix and release it in a timely manner.
