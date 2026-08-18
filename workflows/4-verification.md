# 4 Verification & reporting Workflow

## Purpose
Verification & Reporting

## Canonical Rules & Process
1. **Test Verification**: Run full test suite 3x Measure coverage before/after Check for flaky tests Verify new tests pass
1. **Lint Verification**: Run linter Count violations before/after Verify no new violations
1. **Security Verification**: Run secret scanner Run dependency scanner Run SAST Verify no new findings
1. **Build Verification**: Run build Check for warnings Verify artifacts
1. **Documentation Verification**: Verify all links Check code examples Test setup instructions
1. **Report Generation**: Calculate all metrics Generate summary List followups Provide rollback instructions Generate PR description

## Raw Protocol Data
```yaml
id: phase_4_verification
name: Verification & Reporting
agent: verification_agent
timeout_minutes: 15
steps:
- id: '4.1'
  name: Test Verification
  actions:
  - Run full test suite 3x
  - Measure coverage before/after
  - Check for flaky tests
  - Verify new tests pass
- id: '4.2'
  name: Lint Verification
  actions:
  - Run linter
  - Count violations before/after
  - Verify no new violations
- id: '4.3'
  name: Security Verification
  actions:
  - Run secret scanner
  - Run dependency scanner
  - Run SAST
  - Verify no new findings
- id: '4.4'
  name: Build Verification
  actions:
  - Run build
  - Check for warnings
  - Verify artifacts
- id: '4.5'
  name: Documentation Verification
  actions:
  - Verify all links
  - Check code examples
  - Test setup instructions
- id: '4.6'
  name: Report Generation
  actions:
  - Calculate all metrics
  - Generate summary
  - List followups
  - Provide rollback instructions
  - Generate PR description
```

## Validation
Must comply with `rup-schema.json`.
