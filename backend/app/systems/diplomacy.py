from __future__ import annotations

from typing import Any

from ..catalog import FACTIONS
from ..engine.types import TurnContext, TurnEvent

STANCE_RELATION = {"友善": 70, "中立": 0, "敌对": -60, "战争": -100}


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


def faction_static_info(faction: str) -> dict[str, Any]:
    info = FACTIONS.get(faction, {})
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
    for faction, dynamic in normalize_diplomacy_state(state).items():
        owned_tiles = territory_for_faction(state, faction)
        details[faction] = {
            **faction_static_info(faction),
            **dynamic,
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
