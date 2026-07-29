from __future__ import annotations

from typing import Any

from copy import deepcopy

from ..catalog import DEFAULT_RESOURCES, FACTIONS, UNITS
from ..engine.types import TurnContext, TurnEvent

STANCE_RELATION = {"友善": 70, "中立": 0, "敌对": -60, "战争": -100}
DIPLOMACY_BUILDING_LABELS = {
    "castle": "城堡",
    "town": "城镇",
    "village": "农村",
    "slum": "流民窝棚",
}


def _stance_from_relation(relation: int, at_war: bool = False) -> str:
    if at_war:
        return "战争"
    if relation >= 60:
        return "友善"
    if relation < -30:
        return "敌对"
    return "中立"


def normalize_diplomacy_state(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for faction, value in state.get("diplomacy", {}).items():
        if isinstance(value, dict):
            relation = max(-100, min(100, int(value.get("relation", STANCE_RELATION.get(value.get("stance"), 0)))))
            at_war = bool(value.get("at_war", False))
            treaties = list(value.get("treaties", []))
            normalized[faction] = {
                "stance": value.get("stance") or _stance_from_relation(relation, at_war),
                "relation": relation,
                "treaties": treaties,
                "at_war": at_war,
            }
        else:
            stance = str(value)
            relation = STANCE_RELATION.get(stance, 0)
            normalized[faction] = {
                "stance": stance,
                "relation": relation,
                "treaties": [],
                "at_war": stance == "战争",
            }
    state["diplomacy"] = normalized
    return normalized


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _owned_building_counts(state: dict[str, Any], faction: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tile in state.get("diplomacy_map", []):
        if tile.get("owner") != faction:
            continue
        label = DIPLOMACY_BUILDING_LABELS.get(str(tile.get("kind")))
        if label:
            counts[label] = counts.get(label, 0) + 1
    return counts


def _default_faction_resources(state: dict[str, Any], faction: str, owned_tile_count: int) -> dict[str, int]:
    base = {key: 0 for key in DEFAULT_RESOURCES}
    population = max(80, owned_tile_count * 120)
    base.update({
        "gold": 300 + owned_tile_count * 80,
        "food": 300 + owned_tile_count * 120,
        "wood": 120 + owned_tile_count * 40,
        "stone": 80 + owned_tile_count * 35,
        "iron": 20 + owned_tile_count * 10,
        "meat": 40 + owned_tile_count * 20,
        "leather": 20 + owned_tile_count * 10,
        "craft_goods": 10 + owned_tile_count * 8,
        "tools": 10 + owned_tile_count * 5,
        "piety": 0,
        "security": 50,
        "service_income": 0,
        "authority": 50,
        "morale": 50,
        "population": population,
    })
    info = state.get("factions", {}).get(faction, {})
    if isinstance(info, dict) and info.get("is_player"):
        return {key: _int(state.get("resources", {}).get(key, value), value) for key, value in base.items()}
    return base


def _default_faction_army(dynamic: dict[str, Any], owned_tile_count: int) -> dict[str, int]:
    at_war = bool(dynamic.get("at_war"))
    relation = _int(dynamic.get("relation"), 0)
    multiplier = 2 if at_war else 1
    hostility_bonus = 2 if relation < -30 else 0
    return {
        unit_id: 0
        for unit_id in UNITS
    } | {
        "infantry": max(3, owned_tile_count * 6 * multiplier + hostility_bonus),
        "archers": max(1, owned_tile_count * 2 * multiplier),
        "cavalry": max(0, owned_tile_count * multiplier // 2),
    }


def _normalize_faction_entry(state: dict[str, Any], faction: str, current: dict[str, Any] | None, dynamic: dict[str, Any]) -> dict[str, Any]:
    current = deepcopy(current if isinstance(current, dict) else {})
    static = faction_static_info(faction, state)
    is_player = bool(state.get("factions", {}).get(faction, {}).get("is_player"))
    owned_tiles = territory_for_faction(state, faction)
    default_resources = _default_faction_resources(state, faction, len(owned_tiles))
    resources = current.get("resources") if isinstance(current.get("resources"), dict) else {}
    changes = current.get("changes") if isinstance(current.get("changes"), dict) else {}
    army = current.get("army") if isinstance(current.get("army"), dict) else {}
    buildings = current.get("buildings") if isinstance(current.get("buildings"), dict) else {}
    if is_player:
        resources = deepcopy(state.get("resources", default_resources))
        changes = deepcopy(state.get("changes", {}))
        army = deepcopy(state.get("army", {}))
        buildings = deepcopy(state.get("buildings", {}))
    normalized_resources = {key: _int(resources.get(key, value), value) for key, value in default_resources.items()}
    normalized_changes = {key: _int(changes.get(key, 0), 0) for key in normalized_resources}
    default_army = _default_faction_army(dynamic, len(owned_tiles))
    normalized_army = {unit_id: _int(army.get(unit_id, default_army.get(unit_id, 0)), default_army.get(unit_id, 0)) for unit_id in UNITS}
    owned_buildings = _owned_building_counts(state, faction)
    normalized_buildings = {str(key): _int(value, 0) for key, value in buildings.items()}
    for key, value in owned_buildings.items():
        normalized_buildings.setdefault(key, value)
    workforce = current.get("workforce") if isinstance(current.get("workforce"), dict) else {}
    if is_player:
        workforce = deepcopy(state.get("workforce", workforce))
    return {
        "name": faction,
        "is_player": is_player,
        "color": static["color"],
        "banner": static["banner"],
        "description": static["description"],
        "resources": normalized_resources,
        "changes": normalized_changes,
        "army": normalized_army,
        "army_status": deepcopy(state.get("army_status", {})) if is_player else {
            **{"organization": 100, "routed": False, "last_loss_ratio": 0.0},
            **deepcopy(current.get("army_status") if isinstance(current.get("army_status"), dict) else {}),
        },
        "buildings": normalized_buildings,
        "workforce": {
            "available": _int(workforce.get("available", normalized_resources.get("population", 0)), normalized_resources.get("population", 0)),
            "assigned": _int(workforce.get("assigned", 0), 0),
        },
        "laws": list(state.get("laws", [])) if is_player else list(current.get("laws", []) if isinstance(current.get("laws"), list) else []),
        "construction_queue": deepcopy(state.get("construction_queue", [])) if is_player else deepcopy(current.get("construction_queue", []) if isinstance(current.get("construction_queue"), list) else []),
        "construction_seq": _int(state.get("construction_seq", 0), 0) if is_player else _int(current.get("construction_seq", 0), 0),
        "training_queue": deepcopy(state.get("training_queue", [])) if is_player else deepcopy(current.get("training_queue", []) if isinstance(current.get("training_queue"), list) else []),
        "training_seq": _int(state.get("training_seq", 0), 0) if is_player else _int(current.get("training_seq", 0), 0),
        "territory": {"owned_tile_count": len(owned_tiles), "owned_tiles": owned_tiles},
    }


def normalize_faction_states(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    diplomacy = normalize_diplomacy_state(state)
    raw = state.get("faction_states")
    if not isinstance(raw, dict):
        raw = {}
    normalized: dict[str, dict[str, Any]] = {}
    for faction, dynamic in diplomacy.items():
        normalized[faction] = _normalize_faction_entry(state, faction, raw.get(faction), dynamic)
    state["faction_states"] = normalized
    return normalized


def faction_static_info(faction: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    info = (state or {}).get("factions", {}).get(faction) or FACTIONS.get(faction, {})
    return {
        "color": info.get("color", "#8a8a8a"),
        "banner": info.get("banner", "⚑"),
        "description": info.get("description", ""),
    }


def territory_for_faction(state: dict[str, Any], faction: str) -> list[dict[str, Any]]:
    return [
        {"x": tile["x"], "y": tile["y"], "kind": tile["kind"], "label": tile["label"], "owner": tile.get("owner")}
        for tile in state.get("diplomacy_map", [])
        if tile.get("owner") == faction
    ]


def faction_detail(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {}
    faction_states = normalize_faction_states(state)
    for faction, dynamic in normalize_diplomacy_state(state).items():
        owned_tiles = territory_for_faction(state, faction)
        details[faction] = {
            **faction_static_info(faction, state),
            **dynamic,
            "state": faction_states.get(faction, {}),
            "owned_tiles": owned_tiles,
            "owned_tile_count": len(owned_tiles),
        }
    return details


def change_relation(state: dict[str, Any], faction: str, delta: int, reason: str, context: TurnContext) -> None:
    diplomacy = normalize_diplomacy_state(state)
    entry = diplomacy.setdefault(faction, {"stance": "中立", "relation": 0, "treaties": [], "at_war": False})
    before = int(entry["relation"])
    entry["relation"] = max(-100, min(100, before + int(delta)))
    entry["stance"] = _stance_from_relation(entry["relation"], entry.get("at_war", False))
    context.events.append(TurnEvent(
        phase="diplomacy",
        kind="relation_changed",
        message=f"{faction} 的外交关系变化 {entry['relation'] - before:+d}。",
        data={"faction": faction, "before": before, "after": entry["relation"], "reason": reason},
    ))


def set_stance(state: dict[str, Any], faction: str, stance: str, context: TurnContext | None = None) -> None:
    diplomacy = normalize_diplomacy_state(state)
    relation = STANCE_RELATION.get(stance, 0)
    diplomacy[faction] = {
        "stance": stance,
        "relation": relation,
        "treaties": diplomacy.get(faction, {}).get("treaties", []),
        "at_war": stance == "战争",
    }
    if context is not None:
        context.events.append(TurnEvent(
            phase="diplomacy",
            kind="stance_changed",
            message=f"{faction} 的外交姿态变为{stance}。",
            data={"faction": faction, "stance": stance},
        ))


def add_treaty(state: dict[str, Any], faction: str, treaty: str, duration_turns: int, context: TurnContext) -> None:
    diplomacy = normalize_diplomacy_state(state)
    entry = diplomacy.setdefault(faction, {"stance": "中立", "relation": 0, "treaties": [], "at_war": False})
    entry["treaties"].append({"name": treaty, "remaining_turns": max(1, int(duration_turns))})
    context.events.append(TurnEvent(
        phase="diplomacy",
        kind="treaty_added",
        message=f"{faction} 签署了{treaty}。",
        data={"faction": faction, "treaty": treaty, "duration_turns": duration_turns},
    ))


def advance_treaties(state: dict[str, Any], context: TurnContext) -> None:
    diplomacy = normalize_diplomacy_state(state)
    expired: list[dict[str, str]] = []
    for faction, entry in diplomacy.items():
        active = []
        for treaty in entry.get("treaties", []):
            treaty["remaining_turns"] -= 1
            if treaty["remaining_turns"] <= 0:
                expired.append({"faction": faction, "treaty": treaty["name"]})
            else:
                active.append(treaty)
        entry["treaties"] = active
    if expired:
        context.events.append(TurnEvent(phase="diplomacy", kind="treaties_expired", message="部分外交条约到期。", data={"expired": expired}))
    else:
        context.events.append(TurnEvent(phase="diplomacy", kind="treaties_noop", message="本轮没有外交条约到期。"))


def run_diplomacy_phase(state: dict[str, Any], context: TurnContext) -> None:
    normalize_diplomacy_state(state)
    advance_treaties(state, context)
