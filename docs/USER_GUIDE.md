# Skill-RUP User Guide

## Activating the Skill
When an agent connects to this directory, it should parse `SKILL.md` to understand the workflow rules.

## Using the CLI

The deterministic runtime is accessed via `runtime/cli.py`. You can run the lifecycle phases locally on any repository:

```bash
cd /path/to/Skill-RUP
python3 -m runtime.cli discovery --target /path/to/my-repo
python3 -m runtime.cli plan --target /path/to/my-repo
python3 -m runtime.cli execute --target /path/to/my-repo
python3 -m runtime.cli verify --target /path/to/my-repo
python3 -m runtime.cli report --target /path/to/my-repo
```

## Workflows
The `workflows/` directory contains standard operating procedures (SOPs). Use them when you need rules for specific domains such as `ci-cd`, `bug-fixes`, etc.