from __future__ import annotations

import random
from copy import deepcopy
from typing import Any

from ..catalog import BUILDINGS
from .triggers import legal_build_tiles


def _weighted_choice(values: dict[str, Any], rng: random.Random) -> str:
    rows = [(str(key), max(0, int(weight))) for key, weight in values.items()]
    total = sum(weight for _, weight in rows)
    if total <= 0:
        return rows[0][0]
    marker = rng.randrange(total)
    for value, weight in rows:
        if marker < weight:
            return value
        marker -= weight
    return rows[-1][0]


def generate_parameters(state: dict[str, Any], definition: dict[str, Any], trigger_facts: dict[str, Any], *, seed: int, chain_facts: dict[str, Any] | None = None) -> dict[str, Any]:
    rng = random.Random(seed)
    facts = deepcopy(chain_facts or {})
    params = definition.get("parameters", {})
    building_spec = params.get("building_id", {})
    candidates = trigger_facts.get(str(building_spec.get("from_trigger_result", "")), [])
    if candidates:
        facts["building_id"] = sorted(str(value) for value in candidates)[rng.randrange(len(candidates))]
    for name, spec in params.items():
        if name == "building_id" or not isinstance(spec, dict):
            continue
        if "constant" in spec:
            facts[name] = deepcopy(spec["constant"])
        elif "range" in spec:
            low, high = spec["range"]
            facts[name] = round(rng.uniform(float(low), float(high)), 4)
        elif "weighted_values" in spec:
            facts[name] = _weighted_choice(spec["weighted_values"], rng)
        elif spec.get("from_service") == "legal_build_tiles":
            tiles = legal_build_tiles(state, str(facts.get("building_id", "")))
            if not tiles:
                raise ValueError("参数生成时已无合法建筑地块")
            facts[name] = deepcopy(tiles[rng.randrange(len(tiles))])
    building_id = facts.get("building_id")
    if building_id in BUILDINGS:
        building = BUILDINGS[building_id]
        cost = {str(key): int(value) for key, value in building.get("cost", {}).items()}
        saved_ratio = float(facts.get("saved_gold_ratio", 0.5))
        saved_gold = min(int(cost.get("gold", 0)), max(0, int(round(cost.get("gold", 0) * saved_ratio))))
        facts.update({
            "building_name": building.get("name", building_id), "building_cost": cost,
            "saved_gold": saved_gold,
            "requested_support": {**cost, "gold": max(0, int(cost.get("gold", 0)) - saved_gold)},
            "tile_label": f"{chr(64 + int(facts['tile']['x']))}{int(facts['tile']['y'])}" if isinstance(facts.get("tile"), dict) else "未知地块",
        })
    return facts
