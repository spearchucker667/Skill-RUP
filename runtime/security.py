"""
security module for RUP deterministic runtime.
"""
from pathlib import Path
import yaml
import os

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_YAML_ALIASES = 50

class LimitedAliasLoader(yaml.SafeLoader):
    """SafeLoader with alias expansion limits to prevent YAML bombs."""
    def __init__(self, stream):
        super().__init__(stream)
        self._alias_count = 0

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            self._alias_count += 1
            if self._alias_count > MAX_YAML_ALIASES:
                raise yaml.YAMLError(f"YAML aliases exceed limit ({MAX_YAML_ALIASES}).")
        return super().compose_node(parent, index)

def enforce_path_jail(root: Path, target: Path) -> Path:
    """Ensure target path is within root, resolving symlinks safely."""
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    try:
        resolved_target.relative_to(resolved_root)
    except ValueError:
        raise PermissionError(f"Path traversal detected: {target} escapes {root}")
    return resolved_target

def safe_load_yaml(file_path: Path):
    if file_path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"File too large: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.load(f, Loader=LimitedAliasLoader)

def check_prompt_injection(content: str) -> bool:
    """Basic check for obvious prompt injection attempts."""
    forbidden = ["Ignore previous instructions", "send secrets", "curl http"]
    return any(f.lower() in content.lower() for f in forbidden)
