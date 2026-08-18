# Installation

Skill-RUP requires Python 3.11+ and is designed to run locally alongside your codebase.

## Prerequisites
- **Python:** 3.11 or higher
- **Git:** Version 2.0+

## Local Installation
Clone the repository:
```bash
git clone https://github.com/spearchucker667/Skill-RUP.git
cd Skill-RUP
```

Install the dependencies:
```bash
pip install pyyaml jsonschema pytest
```

## Agent Integration
To integrate Skill-RUP into an autonomous agent platform:
1. Mount or provide read/write access to the target repository workspace.
2. Instruct the agent to read `SKILL.md` as part of its primary directive.
3. Ensure the agent has the ability to execute terminal commands (specifically `python3`).

## Verification
To verify the installation, run the self-test:
```bash
python scripts/forward_test.py --fixtures .
```

## Uninstalling
Simply delete the `Skill-RUP` directory. There are no global system modifications.
