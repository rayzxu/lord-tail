from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from ..catalog import BUILDINGS, POPULATION_CLASSES, UNITS
from ..systems import demographics, diplomacy


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resource_flow(state: Mapping[str, Any]) -> dict[str, float]:
    flow: dict[str, float] = {}
    buildings = state.get("buildings", {})
    for building in BUILDINGS.values():
        count = max(0, int(buildings.get(building["name"], 0) or 0))
        if not count:
            continue
        for resource, amount in building.get("production", {}).items():
            flow[resource] = flow.get(resource, 0.0) + _number(amount) * count
        for resource, amount in building.get("consumption", {}).items():
            flow[resource] = flow.get(resource, 0.0) - _number(amount) * count
        for resource, amount in building.get("maintenance", {}).items():
            flow[resource] = flow.get(resource, 0.0) - _number(amount) * count
    for unit_id, unit in UNITS.items():
        count = max(0, int(state.get("army", {}).get(unit_id, 0) or 0))
        for resource, amount in unit.get("upkeep", {}).items():
            flow[resource] = flow.get(resource, 0.0) - _number(amount) * count
    population = max(0, int(state.get("resources", {}).get("population", 0) or 0))
    flow["food"] = flow.get("food", 0.0) - max(1, population // 10)
    return flow


def _runway_days(current: float, net_per_turn: float, turn_days: int) -> float | None:
    if net_per_turn >= 0:
        return None
    return round(max(0.0, current) / abs(net_per_turn) * max(1, turn_days), 2)


def _army_power(army: Mapping[str, Any], *, defense: bool = False, organization: float = 100) -> float:
    key = "defense" if defense else "power"
    raw = 0.0
    for unit_id, count in army.items():
        unit = UNITS.get(unit_id)
        if not unit:
            continue
        combat = unit.get("combat", {})
        raw += max(0, int(count or 0)) * _number(combat.get(key, combat.get("power", 1)), 1)
    if organization >= 60:
        modifier = 1.0
    elif organization >= 30:
        modifier = 0.8 if defense else 0.75
    elif organization > 0:
        modifier = 0.35
    else:
        modifier = 0.05
    return round(raw * modifier, 2)


def _diplomacy_analysis(state: Mapping[str, Any]) -> dict[str, Any]:
    relations: list[int] = []
    hostile = friendly = wars = alliances = opportunities = 0
    player_name = str(state.get("realm_name", ""))
    for faction, raw in state.get("diplomacy", {}).items():
        info = state.get("factions", {}).get(faction, {})
        if faction == player_name or (isinstance(info, dict) and info.get("is_player")):
            continue
        if isinstance(raw, dict):
            relation = int(raw.get("relation", 0) or 0)
            at_war = bool(raw.get("at_war", False))
            treaties = raw.get("treaties", [])
        else:
            relation = {"友善": 70, "中立": 0, "敌对": -60, "战争": -100}.get(str(raw), 0)
            at_war = str(raw) == "战争"
            treaties = []
        relations.append(relation)
        wars += int(at_war)
        hostile += int(at_war or relation < -30)
        friendly += int(not at_war and relation >= 40)
        opportunities += int(not at_war and relation >= -60)
        alliances += sum(
            1
            for treaty in treaties
            if any(word in str(treaty.get("name") if isinstance(treaty, dict) else treaty) for word in ("联盟", "共同防御"))
        )
    average = round(sum(relations) / len(relations), 2) if relations else 0.0
    war_risk = min(1.0, round((wars * 0.55 + hostile * 0.2 + max(0.0, -average) / 200), 3))
    return {
        "neighbor_count": len(relations),
        "hostile_neighbors": hostile,
        "friendly_neighbors": friendly,
        "at_war_count": wars,
        "average_relation": average,
        "diplomatic_isolation": max(0, len(relations) - friendly),
        "trade_opportunities": opportunities,
        "alliances": alliances,
        "war_risk": war_risk,
    }


def _external_threat(state: Mapping[str, Any]) -> tuple[float, str | None]:
    strongest = 0.0
    strongest_faction: str | None = None
    player_name = str(state.get("realm_name", ""))
    faction_states = state.get("faction_states", {})
    for faction, relation in state.get("diplomacy", {}).items():
        info = state.get("factions", {}).get(faction, {})
        if faction == player_name or (isinstance(info, dict) and info.get("is_player")):
            continue
        dynamic = relation if isinstance(relation, dict) else {}
        relation_value = int(dynamic.get("relation", 0) or 0)
        if not dynamic.get("at_war") and relation_value >= -30:
            continue
        faction_state = faction_states.get(faction, {}) if isinstance(faction_states, Mapping) else {}
        organization = _number(faction_state.get("army_status", {}).get("organization", 100), 100)
        power = _army_power(faction_state.get("army", {}), organization=organization)
        if power > strongest:
            strongest = power
            strongest_faction = str(faction)
    return round(strongest, 2), strongest_faction


def analyze_realm(state: Mapping[str, Any]) -> dict[str, Any]:
    """Return stable derived metrics without mutating the supplied state."""
    snapshot = deepcopy(dict(state))
    diplomacy.normalize_diplomacy_state(snapshot)
    diplomacy.normalize_faction_states(snapshot)
    demographics.normalize_demographics(snapshot)
    demographics.recalculate_housing(snapshot)

    resources = snapshot.get("resources", {})
    turn_days = max(1, int(snapshot.get("time", {}).get("turn_days", 9) or 9))
    flow = _resource_flow(snapshot)
    food_net = round(flow.get("food", 0.0), 2)
    gold_net = round(flow.get("gold", 0.0), 2)
    housing = snapshot.get("demographics", {}).get("housing", {})
    classes = snapshot.get("demographics", {}).get("classes", {})
    working_population = sum(max(0, int(row.get("age", {}).get("working", 0) or 0)) for row in classes.values())
    jobs = 0
    for building in BUILDINGS.values():
        count = max(0, int(snapshot.get("buildings", {}).get(building["name"], 0) or 0))
        jobs += sum(max(0, int(value or 0)) for value in building.get("employment", {}).values()) * count
    employment_rate = round(min(1.0, jobs / max(1, working_population)), 4)

    organization = int(snapshot.get("army_status", {}).get("organization", 100) or 0)
    attack_power = _army_power(snapshot.get("army", {}), organization=organization)
    defensive_power = _army_power(snapshot.get("army", {}), defense=True, organization=organization)
    defensive_power += int(snapshot.get("resources", {}).get("security", 0) or 0) * 0.2
    defensive_power += int(snapshot.get("buildings", {}).get("城墙", 0) or 0) * 5
    external_threat, strongest_faction = _external_threat(snapshot)
    readiness = round(defensive_power / max(external_threat, 1.0), 3)
    diplomacy_metrics = _diplomacy_analysis(snapshot)

    bottlenecks: list[dict[str, Any]] = []
    for building in BUILDINGS.values():
        count = max(0, int(snapshot.get("buildings", {}).get(building["name"], 0) or 0))
        for resource, amount in building.get("consumption", {}).items():
            required = int(amount) * count
            available = int(resources.get(resource, 0) or 0)
            if required > available:
                bottlenecks.append({"resource": resource, "required": required, "available": available, "building": building["name"]})

    project_load = {
        "active_projects": len([item for item in snapshot.get("construction_queue", []) if item.get("status", "active") == "active"]),
        "assigned_workforce": int(snapshot.get("workforce", {}).get("assigned", 0) or 0),
        "available_workforce": int(snapshot.get("workforce", {}).get("available", resources.get("population", 0)) or 0),
    }
    army_size = sum(max(0, int(value or 0)) for value in snapshot.get("army", {}).values())
    finance = {
        "food_net_turn": food_net,
        "food_runway_days": _runway_days(_number(resources.get("food")), food_net, turn_days),
        "gold_net_turn": gold_net,
        "gold_runway_days": _runway_days(_number(resources.get("gold")), gold_net, turn_days),
        "housing_vacant": int(housing.get("total_vacant", 0) or 0),
        "housing_capacity": int(housing.get("total_capacity", 0) or 0),
        "employment_rate": employment_rate,
        "production_bottlenecks": bottlenecks,
        "project_load": project_load,
    }
    military = {
        "army_size": army_size,
        "attack_power": attack_power,
        "defensive_power": round(defensive_power, 2),
        "organization": organization,
        "external_threat": external_threat,
        "strongest_threat_faction": strongest_faction,
        "military_readiness": readiness,
    }
    result = {
        "resources": deepcopy(resources),
        "finance": finance,
        "military": military,
        "diplomacy": diplomacy_metrics,
        "stability": {
            "morale": int(resources.get("morale", 0) or 0),
            "authority": int(resources.get("authority", 0) or 0),
            "security": int(resources.get("security", 0) or 0),
            "population": int(resources.get("population", 0) or 0),
        },
    }
    result["metrics"] = {
        **{key: value for key, value in finance.items() if not isinstance(value, (dict, list))},
        **military,
        **diplomacy_metrics,
        **result["stability"],
    }
    return result
