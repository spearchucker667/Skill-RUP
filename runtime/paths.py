"""
paths module for RUP deterministic runtime.
"""
from pathlib import Path
from .security import enforce_path_jail

class RupPaths:
    def __init__(self, target_dir: Path):
        # The agent skill is installed wherever this runtime module is located
        self.skill_root = Path(__file__).parent.parent.resolve()
        self.target_dir = target_dir.resolve()
        
        if not self.target_dir.is_dir():
            raise NotADirectoryError(f"Target directory not found: {self.target_dir}")

    def get_skill_path(self, *subpaths) -> Path:
        """Resolve a path within the skill's own directory (e.g. protocol/)."""
        target = self.skill_root.joinpath(*subpaths)
        return enforce_path_jail(self.skill_root, target)
        
    def get_target_path(self, *subpaths) -> Path:
        """Resolve a path within the target user repository."""
        target = self.target_dir.joinpath(*subpaths)
        return enforce_path_jail(self.target_dir, target)
        
    @property
    def protocol_dir(self) -> Path:
        return self.get_skill_path("protocol")
        
    @property
    def schemas_dir(self) -> Path:
        return self.get_skill_path("schemas")
        
    @property
    def templates_dir(self) -> Path:
        return self.get_skill_path("templates")
