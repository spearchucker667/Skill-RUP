import subprocess
from pathlib import Path

import pytest

from runtime.command_runner import run_command


def test_successful_command(tmp_path):
    rc, stdout, stderr = run_command(["python", "-c", "print('hello')"], cwd=tmp_path)
    assert rc == 0
    assert "hello" in stdout
    assert stderr == ""


def test_nonzero_exit(tmp_path):
    rc, stdout, stderr = run_command(["python", "-c", "import sys; sys.exit(3)"], cwd=tmp_path)
    assert rc == 3


def test_missing_executable(tmp_path):
    rc, stdout, stderr = run_command(["this_binary_does_not_exist_12345"], cwd=tmp_path)
    assert rc == 127
    assert "Executable not found" in stderr


def test_timeout_with_textual_stdout(tmp_path):
    rc, stdout, stderr = run_command(
        # Flush stdout so the partial output is captured before the timeout.
        ["python", "-c", "import time; print('start', flush=True); time.sleep(10)"],
        cwd=tmp_path,
        timeout=1,
    )
    assert rc == 124
    assert "start" in stdout
    assert "timed out" in stderr.lower() or "timed out" in stdout.lower()


def test_timeout_no_stdout(tmp_path):
    rc, stdout, stderr = run_command(
        ["python", "-c", "import time; time.sleep(10)"],
        cwd=tmp_path,
        timeout=1,
    )
    assert rc == 124
    assert "timed out" in stderr.lower()


def test_invalid_command_type(tmp_path):
    with pytest.raises(TypeError):
        run_command("echo hello", cwd=tmp_path)


def test_invalid_argument_type(tmp_path):
    with pytest.raises(TypeError):
        run_command(["echo", 123], cwd=tmp_path)
