"""
Path resolution and jail enforcement for RUP runtime.
"""
from pathlib import Path
from typing import Optional
from .security import enforce_path_jail

class RupPaths:
    def __init__(self, target_dir: Path, state_dir: Optional[Path] = None):
        self.skill_root = Path(__file__).parent.parent.resolve()
        self.target_dir = target_dir.resolve()

        if not self.target_dir.is_dir():
            raise NotADirectoryError(f"Target directory not found: {self.target_dir}")

        if state_dir is not None:
            resolved_state = state_dir.resolve()
            # Custom state directories must remain inside the target repository.
            try:
                resolved_state.relative_to(self.target_dir)
            except ValueError:
                raise PermissionError(
                    f"State directory must resolve inside the target repository: {resolved_state}"
                )
            self.state_dir = resolved_state
        else:
            self.state_dir = self.target_dir / ".rup"

    def get_skill_path(self, *subpaths) -> Path:
        """Resolve a path within the skill's own directory (e.g. protocol/)."""
        target = self.skill_root.joinpath(*subpaths)
        return enforce_path_jail(self.skill_root, target)
        
    def get_target_path(self, *subpaths) -> Path:
        """Resolve a path within the target user repository."""
        target = self.target_dir.joinpath(*subpaths)
        return enforce_path_jail(self.target_dir, target)

    def get_state_path(self, *subpaths) -> Path:
        """Resolve a path within the controlled state directory (.rup/)."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        target = self.state_dir.joinpath(*subpaths)
        return enforce_path_jail(self.state_dir, target)
        
    @property
    def protocol_dir(self) -> Path:
        return self.get_skill_path("protocol")
        
    @property
    def schemas_dir(self) -> Path:
        return self.get_skill_path("schemas")
        
    @property
    def templates_dir(self) -> Path:
        return self.get_skill_path("templates")

