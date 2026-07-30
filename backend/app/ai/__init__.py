"""Deterministic realm-management AI.

The modules in this package only read or simulate the authoritative game state.
They never call Hermes and never own a second copy of realm data.
"""

from .analysis import analyze_realm
from .actions import execute_action, legal_actions, normalize_action, validate_action
from .planner import plan_management_action

__all__ = [
    "analyze_realm",
    "execute_action",
    "legal_actions",
    "normalize_action",
    "plan_management_action",
    "validate_action",
]
