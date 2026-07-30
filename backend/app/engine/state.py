from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..catalog import (
    BUILDINGS,
    DEFAULT_RESOURCES,
    DIPLOMACY,
    DIPLOMACY_TILE_KINDS,
    FACTIONS,
    MAP_CONFIG,
    MAP_TILE_KINDS,
    TALENTS,
    UNITS,
)
from .mapgen import ensure_player_diplomacy_position, ensure_player_faction, generate_diplomacy_map, generate_realm_map, sanitize_realm_map, validate_generated_maps
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


def infer_custom_map_size(tiles: list[dict[str, Any]]) -> int | None:
    if not tiles:
        return None
    root = int(len(tiles) ** 0.5)
    if root * root == len(tiles):
        return root
    return None


def label_for_kind(kind: str, source: str) -> str:
    catalog = DIPLOMACY_TILE_KINDS if source == "diplomacy" else MAP_TILE_KINDS
    return str(catalog.get(kind, {}).get("label") or kind)


def normalize_submitted_tiles(tiles: list[dict[str, Any]], size: int, source: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in tiles:
        x = int(item.get("x", 0))
        y = int(item.get("y", 0))
        kind = str(item.get("kind", "grass"))
        label = str(item.get("label") or label_for_kind(kind, source))
        owner = item.get("owner") if source == "diplomacy" else None
        normalized.append({"x": x, "y": y, "kind": kind, "label": label, "owner": owner})
    if source == "realm":
        normalized = sanitize_realm_map(normalized)
        center = max(1, (size + 1) // 2)
        for tile in normalized:
            if tile["x"] == center and tile["y"] == center:
                tile.update(kind="castle", label="领主堡垒", owner=None)
                break
    return normalized


def starting_factions_from_request(request: Any) -> dict[str, Any]:
    overrides = getattr(request, "factions", None)
    factions = {} if overrides is not None else deepcopy(FACTIONS)
    overrides = overrides or {}
    diplomacy_overrides = getattr(request, "diplomacy", None) or {}
    for faction in diplomacy_overrides:
        factions.setdefault(str(faction), {"color": "#8a8a8a", "banner": "⚑", "description": ""})
    for faction, value in overrides.items():
        name = str(faction)
        base = factions.setdefault(name, {"color": "#8a8a8a", "banner": "⚑", "description": ""})
        if isinstance(value, dict):
            for key in ("color", "banner", "description"):
                if key in value:
                    base[key] = str(value[key])
    ensure_player_faction(factions, getattr(request, "realm_name", "玩家"))
    return factions


def starting_diplomacy_from_request(request: Any, factions: dict[str, Any]) -> dict[str, Any]:
    requested = getattr(request, "diplomacy", None) or {}
    diplomacy = {faction: deepcopy(DIPLOMACY.get(faction, "中立")) for faction in factions}
    for faction, value in requested.items():
        diplomacy[str(faction)] = deepcopy(value)
    player = ensure_player_faction(factions, getattr(request, "realm_name", "玩家"))
    diplomacy[player] = {"stance": "己方", "relation": 100, "treaties": [], "at_war": False}
    return diplomacy


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
    requested_realm_map = list(getattr(request, "realm_map", []) or [])
    requested_diplomacy_map = list(getattr(request, "diplomacy_map", []) or [])
    inferred_size = infer_custom_map_size(requested_realm_map) or infer_custom_map_size(requested_diplomacy_map)
    map_size = resolve_map_size(getattr(request, "map_size", None) or inferred_size)
    factions = starting_factions_from_request(request)
    realm_map = normalize_submitted_tiles(requested_realm_map, map_size, "realm") if requested_realm_map else initial_map(map_size)
    diplomacy_map = (
        normalize_submitted_tiles(requested_diplomacy_map, map_size, "diplomacy")
        if requested_diplomacy_map
        else generate_diplomacy_map(map_size, factions, player_faction=request.realm_name)
    )
    diplomacy_map = ensure_player_diplomacy_position(diplomacy_map, map_size, request.realm_name)
    state = {
        "realm_name": request.realm_name,
        "lord_name": request.lord_name,
        "lord_gender": request.lord_gender,
        "appearance": request.appearance,
        "personality": request.personality,
        "lord_components": {},
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
        "factions": factions,
        "diplomacy": starting_diplomacy_from_request(request, factions),
        "faction_states": {},
        "buildings": buildings_from_realm_map(realm_map),
        "construction_queue": [],
        "construction_seq": 0,
        "workforce": {"available": resources.get("population", 0), "assigned": 0},
        "laws": [],
        "map_size": map_size,
        "map": realm_map,
        "diplomacy_map_size": map_size,
        "diplomacy_map": diplomacy_map,
        "history": {"entries": [], "next_id": 1},
        "last_history_entries_created": [],
        "scheduled_events": {"entries": [], "next_id": 1},
        "council": {
            "current_meeting": None,
            "history": [],
            "next_id": 1,
            "next_directive_id": 1,
            "last_regular_time": None,
            "last_requested_review_time": None,
            "emergency_cooldowns": {},
        },
        "strategic_directive": None,
        "management_ai": {
            "enabled": True,
            "mode": "delegated",
            "last_decision": None,
            "pending_advice": None,
            "accepted_action": None,
            "consecutive_no_action_turns": 0,
            "action_slot": None,
        },
        "characters": {"entries": [], "next_id": 1},
    }
    from ..systems.characters import normalize_characters
    from ..systems.demographics import normalize_demographics
    from ..systems.diplomacy import normalize_diplomacy_state, normalize_faction_states
    from ..systems.military import normalize_army_status
    from ..systems.scheduled_events import normalize_scheduled_events, schedule_event
    from .history import normalize_history
    from .scenes import normalize_scene_state
    from .time import normalize_time

    normalize_resources(state)
    normalize_map(state)
    normalize_time(state)
    normalize_scene_state(state)
    normalize_army_status(state)
    normalize_diplomacy_state(state)
    normalize_faction_states(state)
    normalize_demographics(state)
    normalize_history(state)
    normalize_scheduled_events(state)
    normalize_characters(state)
    if not state["scheduled_events"]["entries"]:
        schedule_event(
            state,
            event_type="caravan_arrival",
            title="春季末商队到访",
            description_md="春季末，商队将沿着泥泞道路来到领地边界，要求入境贸易。",
            in_days=89,
            created_by="system",
        )
    from ..systems.council import ensure_initial_council

    ensure_initial_council(state)
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
    from ..systems.diplomacy import normalize_diplomacy_state, normalize_faction_states
    from ..systems.military import normalize_army_status
    from ..systems.characters import normalize_characters

    normalize_state(state)
    normalize_army_status(state)
    normalize_diplomacy_state(state)
    normalize_faction_states(state)
    normalize_demographics(state)
    normalize_characters(state)
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
    if not isinstance(state.get("factions"), dict) or not state.get("factions"):
        state["factions"] = deepcopy(FACTIONS)
    factions = state.setdefault("factions", {})
    player = ensure_player_faction(factions, state.get("realm_name", "玩家"))
    diplomacy = state.setdefault("diplomacy", {})
    diplomacy[player] = {"stance": "己方", "relation": 100, "treaties": [], "at_war": False}
    ensure_player_diplomacy_position(diplomacy_tiles, int(size), player)
    validate_generated_maps(state["map"], state["diplomacy_map"], int(size), state.get("factions") or FACTIONS)
    prune_stale_catalog_only_starting_buildings(state)


def normalize_state(state: dict[str, Any]) -> None:
    from ..systems.characters import normalize_characters
    from ..systems.demographics import normalize_demographics
    from ..systems.diplomacy import normalize_diplomacy_state, normalize_faction_states
    from ..systems.military import normalize_army_status
    from ..systems.scheduled_events import normalize_scheduled_events
    from ..systems.council import normalize_council_state
    from .history import normalize_history
    from .scenes import normalize_scene_state
    from .time import normalize_time

    normalize_resources(state)
    normalize_map(state)
    normalize_time(state)
    normalize_scene_state(state)
    normalize_army_status(state)
    normalize_diplomacy_state(state)
    normalize_faction_states(state)
    normalize_demographics(state)
    normalize_history(state)
    normalize_scheduled_events(state)
    normalize_council_state(state)
    normalize_characters(state)


def result(
    state: dict[str, Any],
    narrative: str,
    suggestions: list[str],
    source: str,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalize_state(state)
    return {
        "state": state,
        "narrative": narrative,
        "suggestions": suggestions,
        "source": source,
        "events": events or [],
        "history_entries_created": state.get("last_history_entries_created", []),
    }


def mutation_result(state: dict[str, Any], message: str, events: list[Any] | None = None) -> dict[str, Any]:
    serialized = serialize_events(events) if events else []
    return result(state, message, [], "state-api", serialized)
