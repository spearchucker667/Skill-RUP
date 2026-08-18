"""
Skill-RUP Deterministic Runtime.
Production-Grade Repository Upgrade Framework based on RUP Protocol v3.0.0.
"""

__version__ = "3.0.0"
__protocol_version__ = "3.0.0"

from .paths import RupPaths
from .state import StateManager
from .artifact_builder import ArtifactBuilder
from .command_runner import run_command
from .discovery import DiscoveryPhase
from .planning import PlanningPhase
from .execution import ExecutionPhase
from .verification import VerificationPhase
from .reporting import ReportingPhase

__all__ = [
    "__version__",
    "__protocol_version__",
    "RupPaths",
    "StateManager",
    "ArtifactBuilder",
    "run_command",
    "DiscoveryPhase",
    "PlanningPhase",
    "ExecutionPhase",
    "VerificationPhase",
    "ReportingPhase",
]

