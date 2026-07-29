from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).parent / "data" / "catalog.json"


def _load_catalog() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


CATALOG = _load_catalog()
RESOURCES = CATALOG["resources"]
RESOURCE_KEYS = tuple(RESOURCES.keys())
DEFAULT_RESOURCES = {key: int(value.get("initial", 0)) for key, value in RESOURCES.items()}
TALENTS = CATALOG["talents"]
BUILDINGS = CATALOG["buildings"]
UNITS = CATALOG["units"]
ITEMS = CATALOG.get("items", {})
STARTING_BUILDINGS = CATALOG.get("starting_buildings", {})
DIPLOMACY = CATALOG.get("diplomacy", {})
POPULATION_CLASSES = CATALOG.get("population_classes", {})
MAP_CONFIG = CATALOG.get("map", {"default_size": 10, "min_size": 6, "max_size": 24})
MAP_GENERATION = CATALOG.get("map_generation", {})
MAP_TILE_KINDS = CATALOG.get("map_tile_kinds", {})
DIPLOMACY_TILE_KINDS = CATALOG.get("diplomacy_tile_kinds", {})
FACTIONS = CATALOG.get("factions", {})
EVENT_TEMPLATES = CATALOG.get("event_templates", {})

TALENTS_BY_NAME = {talent["name"]: {"id": key, **talent} for key, talent in TALENTS.items()}
BUILDINGS_BY_NAME = {building["name"]: {"id": key, **building} for key, building in BUILDINGS.items()}
UNITS_BY_NAME = {unit["name"]: {"id": key, **unit} for key, unit in UNITS.items()}
ITEMS_BY_NAME = {item["name"]: {"id": key, **item} for key, item in ITEMS.items()}


def resource_limits(key: str) -> tuple[int, int | None]:
    config = RESOURCES.get(key, {})
    minimum = int(config.get("minimum", 0))
    maximum = config.get("maximum")
    return minimum, int(maximum) if maximum is not None else None


def public_catalog() -> dict[str, Any]:
    return deepcopy(CATALOG)


def validate_map_tile_kinds_catalog() -> None:
    building_kinds = {building["tile_kind"] for building in BUILDINGS.values()}
    missing_kinds = building_kinds - set(MAP_TILE_KINDS.keys())
    if missing_kinds:
        raise ValueError(f"map_tile_kinds 缺少以下建筑地块类型: {sorted(missing_kinds)}")

    diplomacy_required_kinds = {"grass", "forest", "hill", "lake", "river", "town", "village", "slum", "castle"}
    missing_diplomacy_kinds = diplomacy_required_kinds - set(DIPLOMACY_TILE_KINDS.keys())
    if missing_diplomacy_kinds:
        raise ValueError(f"diplomacy_tile_kinds 缺少以下外交地图地块类型: {sorted(missing_diplomacy_kinds)}")

    realm_allowed = set(MAP_GENERATION.get("realm", {}).get("allowed_initial_kinds", []))
    forbidden_realm_kinds = {"hill", "lake", "river", "town", "village", "slum"}
    if realm_allowed & forbidden_realm_kinds:
        raise ValueError(f"map_generation.realm.allowed_initial_kinds 不得包含外交地图地块: {sorted(realm_allowed & forbidden_realm_kinds)}")

    diplomacy_allowed = set(MAP_GENERATION.get("diplomacy", {}).get("allowed_initial_kinds", []))
    economy_building_kinds = {building["tile_kind"] for key, building in BUILDINGS.items() if key not in {"castle", "homes"}}
    if diplomacy_allowed & economy_building_kinds:
        raise ValueError(f"map_generation.diplomacy.allowed_initial_kinds 不得包含经营建筑地块: {sorted(diplomacy_allowed & economy_building_kinds)}")

    faction_keys = set(FACTIONS.keys())
    diplomacy_keys = set(DIPLOMACY.keys())
    if faction_keys != diplomacy_keys:
        raise ValueError(
            "factions 和 diplomacy 的势力集合不一致："
            f"仅在 factions 中={sorted(faction_keys - diplomacy_keys)}，"
            f"仅在 diplomacy 中={sorted(diplomacy_keys - faction_keys)}"
        )
