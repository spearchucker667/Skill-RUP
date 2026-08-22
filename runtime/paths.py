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

        # Custom and default state directories must resolve inside the target
        # repository. In particular the default ``<target>/.rup`` must not be a
        # pre-existing symlink pointing outside the target: resolving it here and
        # verifying containment prevents state/artifact writes from being
        # redirected outside the repository (RUP-SEC-001 write side).
        if state_dir is not None:
            candidate = state_dir
        else:
            candidate = self.target_dir / ".rup"
        resolved_state = candidate.resolve()
        try:
            resolved_state.relative_to(self.target_dir)
        except ValueError:
            raise PermissionError(
                f"State directory must resolve inside the target repository: {resolved_state}"
            )
        self.state_dir = resolved_state

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
        # Re-verify the state root on every access so a symlink swap of .rup/
        # after initialization cannot redirect state writes outside the target.
        resolved_state = self.state_dir.resolve()
        try:
            resolved_state.relative_to(self.target_dir)
        except ValueError:
            raise PermissionError(
                f"State directory escaped the target repository: {resolved_state}"
            )
        resolved_state.mkdir(parents=True, exist_ok=True)
        target = resolved_state.joinpath(*subpaths)
        return enforce_path_jail(resolved_state, target)
        
    @property
    def protocol_dir(self) -> Path:
        return self.get_skill_path("protocol")
        
    @property
    def schemas_dir(self) -> Path:
        return self.get_skill_path("schemas")
        
    @property
    def templates_dir(self) -> Path:
        return self.get_skill_path("templates")

