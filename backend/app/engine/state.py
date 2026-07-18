from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..catalog import BUILDINGS, DEFAULT_RESOURCES, DIPLOMACY, FACTIONS, MAP_CONFIG, TALENTS, UNITS
from .mapgen import generate_diplomacy_map, generate_realm_map, sanitize_realm_map, validate_generated_maps
from .mutations import clamp_resource
from .narrative import serialize_events

SAVE_PATH = Path(__file__).parent.parent.parent / ".lord-tail-save.json"
current_state: dict[str, Any] | None = None


def normalize_resources(state: dict[str, Any]) -> None:
    resources = state.setdefault("resources", {})
    for key, value in DEFAULT_RESOURCES.items():
        resources.setdefault(key, value)
    changes = state.setdefault("changes", {})
    for key in resources:
        changes.setdefault(key, 0)


def resolve_map_size(requested: int | None = None) -> int:
    default_size = int(MAP_CONFIG.get("default_size", 10))
    if requested is None:
        return default_size
    min_size = int(MAP_CONFIG.get("min_size", 6))
    max_size = int(MAP_CONFIG.get("max_size", 24))
    return max(min_size, min(max_size, int(requested)))


def initial_map(size: int | None = None) -> list[dict[str, Any]]:
    return generate_realm_map(resolve_map_size(size))


def initial_diplomacy_map(size: int | None = None) -> list[dict[str, Any]]:
    return generate_diplomacy_map(resolve_map_size(size), FACTIONS)


def buildings_from_realm_map(tiles: list[dict[str, Any]]) -> dict[str, int]:
    by_tile_kind = {building["tile_kind"]: building["name"] for building in BUILDINGS.values()}
    counts: dict[str, int] = {}
    for tile in tiles:
        if tile.get("owner"):
            continue
        name = by_tile_kind.get(str(tile.get("kind")))
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts


_STALE_CATALOG_ONLY_STARTING_BUILDINGS = {"镇屋", "手工作坊", "商店", "宅邸"}


def prune_stale_catalog_only_starting_buildings(state: dict[str, Any]) -> None:
    buildings = state.setdefault("buildings", {})
    map_counts = buildings_from_realm_map(state.get("map", []))
    has_old_catalog_defaults = all(
        int(buildings.get(name, 0)) == 1 and int(map_counts.get(name, 0)) == 0
        for name in _STALE_CATALOG_ONLY_STARTING_BUILDINGS
    )
    if not has_old_catalog_defaults:
        return
    if int(buildings.get("领主堡垒", 0)) < 1 or int(buildings.get("村舍", 0)) < 1:
        return
    for name in _STALE_CATALOG_ONLY_STARTING_BUILDINGS:
        buildings.pop(name, None)
    for name, count in map_counts.items():
        buildings[name] = max(int(buildings.get(name, 0)), count)


def make_state(request: Any) -> dict[str, Any]:
    chosen_talents = [{"id": talent["id"], **TALENTS[talent["id"]]} for talent in request.talents]
    resources = deepcopy(DEFAULT_RESOURCES)
    for talent in chosen_talents:
        for resource, amount in talent["effects"].get("initial_resources", {}).items():
            resources[resource] = clamp_resource(resource, resources.get(resource, 0) + int(amount))
    map_size = resolve_map_size(getattr(request, "map_size", None))
    realm_map = initial_map(map_size)
    state = {
        "realm_name": request.realm_name,
        "lord_name": request.lord_name,
        "lord_gender": request.lord_gender,
        "appearance": request.appearance,
        "personality": request.personality,
        "talents": chosen_talents,
        "turn": 1,
        "season": "春季",
        "weather": "细雨",
        "time": {
            "calendar_day": 1,
            "turn_days": 9,
            "day_in_turn": 1,
            "hour": 6,
            "hour_24": 6,
            "minute": 0,
            "clock": "06:00",
            "clock_24": "06:00",
            "time_of_day": "morning",
            "season": "春季",
            "weather": "细雨",
        },
        "game_mode": "strategic",
        "active_scene": None,
        "scene_seq": 0,
        "resources": resources,
        "changes": {key: 0 for key in resources},
        "army": {unit_id: 0 for unit_id in UNITS},
        "army_status": {"organization": 100, "routed": False, "last_loss_ratio": 0.0},
        "training_queue": [],
        "training_seq": 0,
        "battles": [],
        "diplomacy": deepcopy(DIPLOMACY),
        "buildings": buildings_from_realm_map(realm_map),
        "construction_queue": [],
        "construction_seq": 0,
        "workforce": {"available": resources.get("population", 0), "assigned": 0},
        "laws": [],
        "map_size": map_size,
        "map": realm_map,
        "diplomacy_map_size": map_size,
        "diplomacy_map": initial_diplomacy_map(map_size),
    }
    from ..systems.demographics import normalize_demographics
    from ..systems.diplomacy import normalize_diplomacy_state
    from ..systems.military import normalize_army_status
    from .scenes import normalize_scene_state
    from .time import normalize_time

    normalize_resources(state)
    normalize_map(state)
    normalize_time(state)
    normalize_scene_state(state)
    normalize_army_status(state)
    normalize_diplomacy_state(state)
    normalize_demographics(state)
    return state


def get_current_state() -> dict[str, Any] | None:
    if current_state is not None:
        normalize_state(current_state)
    return current_state


def set_current_state(state: dict[str, Any]) -> dict[str, Any]:
    global current_state
    normalize_state(state)
    current_state = state
    return current_state


def require_state() -> dict[str, Any]:
    if current_state is None:
        raise HTTPException(409, "请先完成领主设定")
    normalize_state(current_state)
    return current_state


def save_current_state() -> None:
    if current_state is None:
        raise HTTPException(409, "没有可保存的游戏")
    SAVE_PATH.write_text(json.dumps(current_state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_current_state() -> dict[str, Any]:
    if not SAVE_PATH.exists():
        raise HTTPException(404, "未找到存档")
    state = json.loads(SAVE_PATH.read_text(encoding="utf-8"))
    from ..systems.demographics import normalize_demographics
    from ..systems.diplomacy import normalize_diplomacy_state
    from ..systems.military import normalize_army_status

    normalize_state(state)
    normalize_army_status(state)
    normalize_diplomacy_state(state)
    normalize_demographics(state)
    return set_current_state(state)


def normalize_map(state: dict[str, Any]) -> None:
    original_tiles = state.setdefault("map", initial_map())
    migrated_diplomacy_tiles = [deepcopy(tile) for tile in original_tiles if tile.get("owner")]
    tiles = sanitize_realm_map(original_tiles)
    state["map"] = tiles
    size = state.get("map_size")
    if not size:
        size = int(round(len(tiles) ** 0.5)) if tiles else resolve_map_size()
    size = resolve_map_size(int(size))
    state["map_size"] = size
    if len(tiles) != size * size:
        tiles = initial_map(size)
        state["map"] = tiles
    diplomacy_tiles = state.get("diplomacy_map")
    if not diplomacy_tiles or len(diplomacy_tiles) != size * size:
        diplomacy_tiles = initial_diplomacy_map(size)
        if migrated_diplomacy_tiles:
            by_coord = {(tile["x"], tile["y"]): tile for tile in diplomacy_tiles}
            for old_tile in migrated_diplomacy_tiles:
                target = by_coord.get((old_tile["x"], old_tile["y"]))
                if target is not None:
                    target.update(old_tile)
        state["diplomacy_map"] = diplomacy_tiles
    for tile in diplomacy_tiles:
        tile.setdefault("owner", None)
    state["diplomacy_map_size"] = state.get("diplomacy_map_size") or size
    validate_generated_maps(state["map"], state["diplomacy_map"], int(size))
    prune_stale_catalog_only_starting_buildings(state)


def normalize_state(state: dict[str, Any]) -> None:
    from ..systems.demographics import normalize_demographics
    from ..systems.diplomacy import normalize_diplomacy_state
    from ..systems.military import normalize_army_status
    from .scenes import normalize_scene_state
    from .time import normalize_time

    normalize_resources(state)
    normalize_map(state)
    normalize_time(state)
    normalize_scene_state(state)
    normalize_army_status(state)
    normalize_diplomacy_state(state)
    normalize_demographics(state)


def result(
    state: dict[str, Any],
    narrative: str,
    suggestions: list[str],
    source: str,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {"state": state, "narrative": narrative, "suggestions": suggestions, "source": source, "events": events or []}


def mutation_result(state: dict[str, Any], message: str, events: list[Any] | None = None) -> dict[str, Any]:
    serialized = serialize_events(events) if events else []
    return result(state, message, [], "state-api", serialized)
