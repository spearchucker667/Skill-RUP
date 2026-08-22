"""Regression tests for the forward-test runner's host-tool policy."""
import json
from pathlib import Path

from scripts import forward_test


def _write_pulumi_result(target: Path, *, passed: bool) -> None:
    state_dir = target / ".rup"
    state_dir.mkdir(parents=True)
    (state_dir / "RUP_VERIFICATION.json").write_text(
        json.dumps(
            {
                "audit_trail": [
                    {
                        "details": {
                            "gates": {
                                "iac_scan": {
                                    "executed": True,
                                    "passed": passed,
                                    "operations": {
                                        "pulumi_preview": {
                                            "executed": True,
                                            "passed": passed,
                                        }
                                    },
                                }
                            }
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_generic_forward_fixture_does_not_depend_on_preinstalled_pulumi(
    tmp_path: Path, monkeypatch
) -> None:
    """An unconfigured Pulumi binary on the host must not fail generic CI."""
    _write_pulumi_result(tmp_path, passed=False)
    monkeypatch.setattr(forward_test.shutil, "which", lambda _tool: "/usr/bin/pulumi")

    assert forward_test.check_fixture_specific(tmp_path, "pulumi_project") == []


def test_dedicated_iac_mode_requires_pulumi_success(tmp_path: Path) -> None:
    """The explicit real-IaC mode retains a strict semantic assertion."""
    _write_pulumi_result(tmp_path, passed=False)

    errors = forward_test.check_fixture_specific(
        tmp_path,
        "pulumi_project",
        require_iac_success=True,
    )

    assert len(errors) == 1
    assert "iac_scan should pass" in errors[0]
