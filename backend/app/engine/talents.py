from __future__ import annotations

from typing import Any


def talent_effect(state: dict[str, Any], effect: str, target: str, default: float = 1) -> float:
    value = default
    for talent in state["talents"]:
        modifier = talent.get("effects", {}).get(effect, {})
        if isinstance(modifier, dict):
            value *= modifier.get(target, modifier.get("all", 1))
    return value


def talent_bonus(state: dict[str, Any], effect: str) -> int:
    return sum(int(talent.get("effects", {}).get(effect, 0)) for talent in state["talents"])


def talent_multiplier(state: dict[str, Any], effect: str, default: float = 1.0) -> float:
    value = default
    for talent in state["talents"]:
        modifier = talent.get("effects", {}).get(effect)
        if isinstance(modifier, (int, float)):
            value *= modifier
    return value
