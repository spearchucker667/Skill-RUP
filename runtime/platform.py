"""
Cross-platform environment, OS abstraction, and execution resolution for RUP runtime.
"""
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Dict, Any, Optional

def get_platform_info() -> Dict[str, Any]:
    """Retrieve platform environment details deterministically."""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "is_windows": is_windows(),
        "is_macos": is_macos(),
        "is_linux": is_linux(),
    }

def is_windows() -> bool:
    return platform.system() == "Windows"

def is_macos() -> bool:
    return platform.system() == "Darwin"

def is_linux() -> bool:
    return platform.system() == "Linux"

def get_python_executable() -> str:
    """Always use sys.executable for deterministic runtime invocation."""
    return sys.executable

def find_executable(name: str, extra_paths: Optional[list] = None) -> Optional[str]:
    """Find executable in PATH or extra search paths."""
    path_env = os.environ.get("PATH", "")
    if extra_paths:
        path_env = os.pathsep.join(extra_paths) + os.pathsep + path_env
    return shutil.which(name, path=path_env)

