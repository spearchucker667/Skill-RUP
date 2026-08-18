"""
Deterministic Markdown artifact builder for RUP runtime.
Renders clean, GitHub-flavored Markdown matching canonical RUP Protocol v3.0.0 templates.
"""
import json
from pathlib import Path
from typing import Dict, Any, List
from .paths import RupPaths

class ArtifactBuilder:
    def __init__(self, paths: RupPaths):
        self.paths = paths

    def build_markdown(self, template_name: str, data: Dict[str, Any], output_filename: str) -> Path:
        """Render deterministic Markdown based on phase data."""
        if "discovery" in template_name.lower():
            content = self._render_discovery_report(data)
        elif "plan" in template_name.lower():
            content = self._render_plan(data)
        elif "execution" in template_name.lower():
            content = self._render_execution_report(data)
        elif "verification" in template_name.lower():
            content = self._render_verification_report(data)
        elif "final" in template_name.lower():
            content = self._render_final_report(data)
        else:
            content = self._render_generic(template_name, data)

        out_path = self.paths.get_state_path(output_filename)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)

        return out_path

    def _render_discovery_report(self, data: Dict[str, Any]) -> str:
        meta = data.get("repo_metadata", {})
        risk = data.get("risk_assessment", {})
        languages = data.get("languages", [])
        tooling = data.get("tooling", {})
        gaps = data.get("gaps", [])

        lang_rows = []
        for l in languages:
            lock_str = "Yes" if l.get("lockfile_present") else "No"
            lang_rows.append(f"| {l.get('name', 'N/A')} | {l.get('percentage', 0)}% | {lock_str} |")
        lang_table = "\n".join(lang_rows) if lang_rows else "| None | 0% | No |"

        tool_rows = []
        for k, v in tooling.items():
            tool_rows.append(f"| {k.replace('_', ' ').title()} | {v} |")
        tool_table = "\n".join(tool_rows) if tool_rows else "| None | None |"

        gap_rows = []
        for g in gaps:
            gap_rows.append(f"| {g.get('id', '')} | {g.get('title', '')} | {g.get('severity', '').upper()} | {g.get('impact', '')} | {g.get('effort_estimate', '')} |")
        gap_table = "\n".join(gap_rows) if gap_rows else "| None | No critical gaps identified | - | - | - |"

        risk_rows = []
        for rf in risk.get("risk_factors", []):
            risk_rows.append(f"| {rf.get('factor', '')} | {rf.get('severity', '').upper()} | {rf.get('mitigation', '')} |")
        risk_table = "\n".join(risk_rows) if risk_rows else "| None | LOW | Standard maintenance |"

        return f"""# DISCOVERY REPORT

## Executive Summary
- **Repository**: {meta.get('name', 'Unknown')}
- **Type**: {meta.get('repo_type', 'Application')}
- **Primary Language**: {meta.get('primary_language', 'Unknown')}
- **Production Readiness**: {risk.get('production_readiness_score', 100)}/100
- **Technical Debt**: {risk.get('technical_debt_score', 0)}/100
- **Overall Risk**: {risk.get('overall_risk', 'low').upper()}

## Repository Metadata
| Property | Value |
|----------|-------|
| Lines of Code | {meta.get('loc', 0):,} |
| Files | {meta.get('file_count', 0)} |
| Contributors | {meta.get('contributors', 1)} |
| Last Commit | {meta.get('last_commit', 'N/A')} |
| Open Issues | {meta.get('open_issues', 0)} |
| License | {meta.get('license', 'UNKNOWN')} |

## Languages
| Language | % | Lockfile Present |
|----------|---|------------------|
{lang_table}

## Tooling
| Capability | Configured Tool |
|------------|-----------------|
{tool_table}

## Critical Gaps
| ID | Gap Title | Severity | Impact | Effort |
|----|-----------|----------|--------|--------|
{gap_table}

## Risk Assessment
| Risk Factor | Severity | Mitigation |
|-------------|----------|------------|
{risk_table}
"""

    def _render_plan(self, data: Dict[str, Any]) -> str:
        constraints = data.get("constraints", {})
        backlog = data.get("backlog", [])
        selected_ids = set(data.get("selected_items", []))
        execution_order = data.get("execution_order", [])
        risk = data.get("risk_analysis", {})

        p0 = [b for b in backlog if b.get("priority") == "P0"]
        p1 = [b for b in backlog if b.get("priority") == "P1"]
        p2 = [b for b in backlog if b.get("priority") == "P2"]
        p3 = [b for b in backlog if b.get("priority") == "P3"]

        def format_items(items):
            if not items:
                return "_None_"
            return "\n".join(f"- **{i.get('id')}**: {i.get('title')} ({i.get('estimated_effort_minutes')}m, Risk: {i.get('risk')})" for i in items)

        selected_rows = []
        for b in backlog:
            if b["id"] in selected_ids:
                selected_rows.append(f"| {b.get('id')} | {b.get('title')} | {b.get('estimated_effort_minutes')}m | {b.get('risk')} | {b.get('priority')} |")
        selected_table = "\n".join(selected_rows) if selected_rows else "| None | - | - | - | - |"

        exec_order_list = "\n".join(f"{idx+1}. `{item_id}`" for idx, item_id in enumerate(execution_order)) if execution_order else "_None_"

        return f"""# PLAN

## Constraints
- **Time Budget**: {constraints.get('time_budget_minutes', 45)} minutes
- **Max Files**: {constraints.get('max_files', 20)}
- **Risk Tolerance**: {constraints.get('risk_tolerance', 'medium')}

## Backlog

### P0 (Critical) — {len(p0)} items
{format_items(p0)}

### P1 (High) — {len(p1)} items
{format_items(p1)}

### P2 (Medium) — {len(p2)} items
{format_items(p2)}

### P3 (Low) — {len(p3)} items
{format_items(p3)}

## Selected for This Run
| ID | Title | Effort | Risk | Priority |
|----|-------|--------|------|----------|
{selected_table}

## Execution Order
{exec_order_list}

## Risk Analysis
- **Breaking Changes Possible**: {risk.get('breaking_changes_possible', False)}
- **Manual Review Required**: {risk.get('requires_manual_review', False)}
- **Rollback Complexity**: {risk.get('rollback_complexity', 'low')}
"""

    def _render_execution_report(self, data: Dict[str, Any]) -> str:
        changes = data.get("changes", [])
        commits = data.get("commits", [])

        change_rows = []
        for c in changes:
            change_rows.append(f"| `{c.get('file_path')}` | {c.get('change_type', '').upper()} | {c.get('rationale')} | {c.get('backlog_item_id')} |")
        change_table = "\n".join(change_rows) if change_rows else "| None | - | No file changes recorded | - |"

        commit_rows = []
        for cm in commits:
            commit_rows.append(f"| `{cm.get('hash')}` | {cm.get('message')} | {'Yes' if cm.get('breaking') else 'No'} |")
        commit_table = "\n".join(commit_rows) if commit_rows else "| None | No commits recorded | No |"

        return f"""# EXECUTION REPORT

## Summary
- **Total Changes**: {len(changes)}
- **Commits Evaluated**: {len(commits)}

## Changes Made
| File Path | Action | Rationale | Backlog Item ID |
|-----------|--------|-----------|-----------------|
{change_table}

## Commits
| Commit Hash | Message | Breaking |
|-------------|---------|----------|
{commit_table}
"""

    def _render_verification_report(self, data: Dict[str, Any]) -> str:
        ver_results = data.get("verification_results", {})
        tests = ver_results.get("tests", {})
        sec = ver_results.get("security", {})
        lint = ver_results.get("lint", {})
        metrics = data.get("metrics", {})
        audit = data.get("audit_trail", [{}])[0]

        return f"""# VERIFICATION REPORT

## Overall Status: {ver_results.get('overall_status', 'unknown').upper()}

## Test Results
| Metric | Result |
|--------|--------|
| Executed | {'Yes' if tests.get('executed') else 'No'} |
| Passed Tests | {tests.get('passed', 0)} |
| Failed Tests | {tests.get('failed', 0)} |
| Skipped Tests | {tests.get('skipped', 0)} |
| Duration | {tests.get('duration_seconds', 0.0)}s |
| Flakiness | {', '.join(tests.get('flaky_tests', [])) or 'None'} |

## Security Verification
| Scanner | Executed | Status | Findings |
|---------|----------|--------|----------|
| Secret Scanner | {'Yes' if sec.get('secret_scan', {}).get('executed') else 'No'} | {'PASSED' if sec.get('secret_scan', {}).get('passed') else 'FAILED'} | {sec.get('secret_scan', {}).get('findings', 0)} |
| SAST Injection Defense | {'Yes' if sec.get('sast_scan', {}).get('executed') else 'No'} | {'PASSED' if sec.get('sast_scan', {}).get('passed') else 'FAILED'} | {sec.get('sast_scan', {}).get('findings', 0)} |
| Dependency Vulnerabilities | {'Yes' if sec.get('dependency_scan', {}).get('executed') else 'No'} | {'PASSED' if sec.get('dependency_scan', {}).get('passed') else 'FAILED'} | {sec.get('dependency_scan', {}).get('critical', 0)} critical |

## Lint Verification
- **Executed**: {'Yes' if lint.get('executed') else 'No'}
- **Violations**: {lint.get('violations_after', 0)}

## Metrics & Diffs
- **Files Changed**: {metrics.get('files_changed', 0)}
- **Lines Added**: {metrics.get('lines_added', 0)}
- **Lines Removed**: {metrics.get('lines_removed', 0)}

## Audit Message
{audit.get('details', {}).get('message', 'Verification completed.')}
"""

    def _render_final_report(self, data: Dict[str, Any]) -> str:
        summary = data.get("summary", {})
        metrics = data.get("metrics", {})
        changes = data.get("changes_summary", [])
        followups = data.get("followups", [])
        rollback = data.get("rollback_procedure", {})
        instructions = data.get("handoff_instructions", "")

        change_rows = []
        for c in changes:
            change_rows.append(f"- **`{c.get('file')}`** ({c.get('type')}): {c.get('rationale')}")
        changes_list = "\n".join(change_rows) if change_rows else "- No changes recorded."

        followup_rows = []
        for f in followups:
            followup_rows.append(f"| {f.get('id')} | {f.get('priority')} | {f.get('title')} | {f.get('estimated_effort_minutes')}m |")
        followup_table = "\n".join(followup_rows) if followup_rows else "| None | - | No follow-ups remaining | - |"

        rollback_cmds = "\n".join(rollback.get("commands", ["# No rollback commands"]))

        return f"""# FINAL REPORT

## Executive Summary
- **Overall Status**: {summary.get('overall_status', 'unknown').upper()}
- **Total Items Processed**: {summary.get('total_items_processed', 0)}
- **Total Changes**: {summary.get('total_changes', 0)}
- **Ready for Submission**: {'Yes' if summary.get('ready_for_submission') else 'No'}

## Metrics
| Metric | Value |
|--------|-------|
| Production Readiness Score | {metrics.get('production_readiness_score', 100)}/100 |
| Technical Debt Score | {metrics.get('technical_debt_score', 0)}/100 |
| Files Changed | {metrics.get('files_changed', 0)} |
| Lines Added | {metrics.get('lines_added', 0)} |
| Lines Removed | {metrics.get('lines_removed', 0)} |
| Tests Passed | {metrics.get('tests_passed', 0)} |
| Tests Failed | {metrics.get('tests_failed', 0)} |

## Changes Made
{changes_list}

## Follow-up Workstream Items
| ID | Priority | Title | Effort |
|----|----------|-------|--------|
{followup_table}

## Rollback Procedure
```bash
{rollback_cmds}
```

## Handoff Instructions
{instructions}
"""

    def _render_generic(self, title: str, data: Dict[str, Any]) -> str:
        clean_title = title.replace(".md", "").replace("_", " ").replace("-", " ").title()
        return f"""# {clean_title}

```json
{json.dumps(data, indent=2)}
```
"""

