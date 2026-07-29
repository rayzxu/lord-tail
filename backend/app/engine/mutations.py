from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..catalog import BUILDINGS, BUILDINGS_BY_NAME, RESOURCE_KEYS, UNITS, UNITS_BY_NAME, resource_limits


def clamp_resource(key: str, value: int) -> int:
    minimum, maximum = resource_limits(key)
    value = max(minimum, int(value))
    return min(maximum, value) if maximum is not None else value


def ensure_resource_key(key: str) -> None:
    if key not in RESOURCE_KEYS:
        raise HTTPException(422, f"未知资源：{key}")


def ensure_changes(state: dict[str, Any]) -> dict[str, int]:
    state.setdefault("changes", {})
    for key in state.get("resources", {}):
        state["changes"].setdefault(key, 0)
    return state["changes"]


def change_resource(resources: dict[str, int], changes: dict[str, int], key: str, amount: int) -> None:
    resources[key] = clamp_resource(key, resources.get(key, 0) + amount)
    changes[key] = changes.get(key, 0) + amount


def set_resource(state: dict[str, Any], key: str, value: int) -> None:
    ensure_resource_key(key)
    resources, changes = state["resources"], ensure_changes(state)
    old_value = int(resources.get(key, 0))
    new_value = clamp_resource(key, value)
    resources[key] = new_value
    changes[key] = changes.get(key, 0) + new_value - old_value


def apply_value_delta(state: dict[str, Any], key: str, request: Any) -> None:
    if request.value is None and request.delta is None:
        raise HTTPException(422, "必须提供 value 或 delta")
    if request.value is not None:
        set_resource(state, key, request.value)
    if request.delta is not None:
        ensure_resource_key(key)
        change_resource(state["resources"], ensure_changes(state), key, request.delta)


def can_pay(resources: dict[str, int], cost: dict[str, int], multiplier: int = 1) -> bool:
    return all(resources.get(resource, 0) >= amount * multiplier for resource, amount in cost.items())


def pay(resources: dict[str, int], changes: dict[str, int], cost: dict[str, int], multiplier: int = 1) -> None:
    for resource, amount in cost.items():
        change_resource(resources, changes, resource, -amount * multiplier)


def resolve_unit(unit_key_or_name: str) -> tuple[str, dict[str, Any]]:
    if unit_key_or_name in UNITS:
        return unit_key_or_name, UNITS[unit_key_or_name]
    unit = UNITS_BY_NAME.get(unit_key_or_name)
    if unit:
        return unit["id"], unit
    raise HTTPException(422, f"未知兵种：{unit_key_or_name}")


def resolve_building(building_key_or_name: str) -> tuple[str, dict[str, Any]]:
    if building_key_or_name in BUILDINGS:
        return building_key_or_name, BUILDINGS[building_key_or_name]
    building = BUILDINGS_BY_NAME.get(building_key_or_name)
    if building:
        return building["id"], building
    raise HTTPException(422, f"未知建筑：{building_key_or_name}")


def tile_at(state: dict[str, Any], x: int, y: int) -> dict[str, Any] | None:
    size = int(state.get("map_size", 10))
    if x < 1 or y < 1 or x > size or y > size:
        raise HTTPException(422, "坐标超出领地地图范围")
    return next((tile for tile in state["map"] if tile["x"] == x and tile["y"] == y), None)


def update_tile_for_building(
    state: dict[str, Any],
    building: dict[str, Any],
    x: int | None,
    y: int | None,
    destroy: bool = False,
) -> None:
    if x is None or y is None:
        return
    tile = tile_at(state, x, y)
    if tile is None:
        raise HTTPException(422, "建筑坐标不在地图范围内")
    if tile.get("owner"):
        raise HTTPException(422, "该地块不属于领主直辖，无法建设")
    if destroy:
        if tile.get("kind") != building["tile_kind"] and tile.get("label") != building["name"]:
            raise HTTPException(422, f"坐标上没有可摧毁的{building['name']}")
        tile.update(kind="grass", label="草地")
    else:
        tile.update(kind=building["tile_kind"], label=building["name"])


def apply_state_patch(state: dict[str, Any], patch: dict[str, Any]) -> None:
    if isinstance(patch.get("resources"), dict):
        for resource, value in patch["resources"].items():
            set_resource(state, resource, int(value))
    if isinstance(patch.get("army"), dict):
        for unit_key_or_name, value in patch["army"].items():
            unit_id, _ = resolve_unit(unit_key_or_name)
            state["army"][unit_id] = max(0, int(value))
    if isinstance(patch.get("diplomacy"), dict):
        from ..systems.diplomacy import set_stance

        for faction, status in patch["diplomacy"].items():
            if isinstance(status, dict):
                state["diplomacy"][str(faction)] = status
            else:
                set_stance(state, str(faction), str(status))
    if isinstance(patch.get("buildings"), dict):
        for building_key_or_name, value in patch["buildings"].items():
            _, building = resolve_building(building_key_or_name)
            state["buildings"][building["name"]] = max(0, int(value))
    if isinstance(patch.get("laws"), list):
        state["laws"] = [str(law)[:120] for law in patch["laws"]]


def _apply_population_delta(state: dict[str, Any], value: int | None = None, delta: int | None = None) -> None:
    from ..systems import demographics

    old_population = int(state["resources"].get("population", 0))
    if value is not None:
        demographics.set_total_population(state, int(value))
    if delta is not None:
        demographics.change_total_population(state, int(delta))
    new_population = int(state["resources"].get("population", 0))
    ensure_changes(state)["population"] = ensure_changes(state).get("population", 0) + new_population - old_population


def apply_structured_action(state: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    from ..systems import demographics, diplomacy, military

    action_type = str(action.get("type", ""))
    payload = action.get("payload", {})
    if not isinstance(payload, dict):
        raise HTTPException(422, "书记官差事内容必须是对象")

    if action_type == "resources":
        for resource, value in payload.get("values", {}).items():
            if resource == "population":
                _apply_population_delta(state, value=int(value))
            else:
                set_resource(state, resource, int(value))
        for resource, delta in payload.get("changes", {}).items():
            if resource == "population":
                _apply_population_delta(state, delta=int(delta))
            else:
                ensure_resource_key(resource)
                change_resource(state["resources"], ensure_changes(state), resource, int(delta))
        return {"type": action_type, "status": "applied"}

    if action_type == "population":
        if payload.get("value") is None and payload.get("delta") is None:
            raise HTTPException(422, "population action 必须提供 value 或 delta")
        _apply_population_delta(state, payload.get("value"), payload.get("delta"))
        return {"type": action_type, "status": "applied"}

    if action_type == "morale":
        request = type("ValueDelta", (), {"value": payload.get("value"), "delta": payload.get("delta")})()
        apply_value_delta(state, "morale", request)
        return {"type": action_type, "status": "applied"}

    if action_type == "army":
        unit = payload.get("unit")
        if not unit:
            raise HTTPException(422, "army action 必须提供 unit")
        unit_id, _ = resolve_unit(str(unit))
        current = int(state.setdefault("army", {}).get(unit_id, 0))
        if payload.get("value") is not None:
            current = int(payload["value"])
        if payload.get("delta") is not None:
            current += int(payload["delta"])
        military.set_unit_count(state, unit_id, current)
        return {"type": action_type, "status": "applied", "unit_id": unit_id}

    if action_type == "diplomacy":
        faction = payload.get("faction")
        status = payload.get("status")
        if not faction or not status:
            raise HTTPException(422, "diplomacy action 必须提供 faction 和 status")
        diplomacy.set_stance(state, str(faction), str(status))
        return {"type": action_type, "status": "applied", "faction": str(faction)}

    if action_type == "buildings":
        building_key = payload.get("building")
        action_name = payload.get("action")
        if not building_key or action_name not in {"build", "destroy"}:
            raise HTTPException(422, "buildings action 必须提供 building 和 build/destroy")
        _, building = resolve_building(str(building_key))
        count = max(1, int(payload.get("count", 1)))
        name = building["name"]
        current = int(state.setdefault("buildings", {}).get(name, 0))
        if action_name == "build":
            state["buildings"][name] = current + count
            update_tile_for_building(state, building, payload.get("x"), payload.get("y"))
        else:
            state["buildings"][name] = max(0, current - count)
            update_tile_for_building(state, building, payload.get("x"), payload.get("y"), destroy=True)
        demographics.recalculate_housing(state)
        return {"type": action_type, "status": "applied", "building": name}

    raise HTTPException(422, f"未知书记官差事类型：{action_type}")
