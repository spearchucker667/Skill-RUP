import sys
from pathlib import Path

def test_python_version():
    """Ensure Python 3.11+ is required."""
    assert sys.version_info >= (3, 11)

def test_no_hardcoded_tmp():
    """Ensure runtime modules don't hardcode /tmp."""
    runtime_dir = Path(__file__).parent.parent.parent / "runtime"
    for py_file in runtime_dir.glob("*.py"):
        content = py_file.read_text()
        assert "='/tmp" not in content
        assert '="/tmp' not in content
