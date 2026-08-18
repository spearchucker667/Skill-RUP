# 4 Verification Workflow

## Purpose
No description provided.

## Canonical Rules & Process
1. **Test Verification**: 
1. **Lint Verification**: 
1. **Security Verification**: 
1. **Build Verification**: 
1. **Documentation Verification**: 
1. **Report Generation**: 

## Raw Protocol Data
```yaml
agent: verification_agent
id: phase_4_verification
name: Verification & Reporting
output_template: '# VERIFICATION REPORT


  ## Overall Status: {status}


  ## Test Results

  | Metric | Before | After | Delta | Target | Status |

  |--------|--------|-------|-------|--------|--------|

  | Coverage | {before}% | {after}% | {delta}% | +5% | {status} |

  | Passing | {before} | {after} | {delta} | 100% | {status} |

  | Flaky | {before} | {after} | {delta} | 0 | {status} |


  ## Security Results

  | Scan | Status | Findings |

  |------|--------|----------|

  | Secrets | {status} | {count} |

  | Dependencies | {status} | {count} |

  | SAST | {status} | {count} |


  ## Lint Results

  - **Before**: {before} violations

  - **After**: {after} violations

  - **New**: {new} violations


  ## Build Results

  - **Status**: {status}

  - **Warnings**: {warnings}

  - **Duration**: {duration}


  ---


  # FINAL REPORT


  ## Executive Summary

  {summary}


  ## Changes Made

  {changes_summary}


  ## Metrics

  {metrics_table}


  ## Assumptions

  {assumptions}


  ## Known Limitations

  {limitations}


  ## Follow-ups

  {followups}


  ## Rollback Procedure

  ```bash

  {rollback_commands}

  ```


  ## PR Ready

  - **Title**: {pr_title}

  - **Labels**: {pr_labels}

  - **Description**: {pr_description}

  '
steps:
- actions:
  - Run full test suite 3x
  - Measure coverage before/after
  - Check for flaky tests
  - Verify new tests pass
  id: '4.1'
  name: Test Verification
- actions:
  - Run linter
  - Count violations before/after
  - Verify no new violations
  id: '4.2'
  name: Lint Verification
- actions:
  - Run secret scanner
  - Run dependency scanner
  - Run SAST
  - Verify no new findings
  id: '4.3'
  name: Security Verification
- actions:
  - Run build
  - Check for warnings
  - Verify artifacts
  id: '4.4'
  name: Build Verification
- actions:
  - Verify all links
  - Check code examples
  - Test setup instructions
  id: '4.5'
  name: Documentation Verification
- actions:
  - Calculate all metrics
  - Generate summary
  - List followups
  - Provide rollback instructions
  - Generate PR description
  id: '4.6'
  name: Report Generation
timeout_minutes: 15

```

## Validation
Must comply with `rup-schema.json`.
