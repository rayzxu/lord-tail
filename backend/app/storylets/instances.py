from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException


def instance_by_id(state: dict[str, Any], instance_id: str) -> dict[str, Any]:
    for instance in state.get("storylets", {}).get("instances", []):
        if instance.get("id") == instance_id:
            return instance
    raise HTTPException(404, "未找到剧情事件")


def public_choice(choice: dict[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in choice.items() if key != "effects"}


def public_instance(instance: dict[str, Any], definition: dict[str, Any] | None = None) -> dict[str, Any]:
    result = deepcopy(instance)
    if definition is not None:
        allowed = set(instance.get("choice_ids", []))
        result["choices"] = [public_choice(choice) for choice in definition.get("choices", []) if choice.get("id") in allowed]
    return result
