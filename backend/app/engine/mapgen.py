from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..catalog import BUILDINGS, DIPLOMACY_TILE_KINDS, FACTIONS, MAP_GENERATION, MAP_TILE_KINDS

REALM_FORBIDDEN_KINDS = {"town", "village", "slum", "hill", "lake", "river"}
DIPLOMACY_SETTLEMENT_LABELS = {"village": "农村", "castle": "城堡", "town": "城镇", "slum": "流民窝棚"}
DIPLOMACY_ECONOMY_BUILDING_KINDS = {
    building["tile_kind"]
    for key, building in BUILDINGS.items()
    if key not in {"castle", "homes"}
}


def _base_tiles(size: int) -> list[dict[str, Any]]:
    return [
        {"x": x, "y": y, "kind": "grass", "label": "草地", "owner": None}
        for y in range(1, size + 1)
        for x in range(1, size + 1)
    ]


def _by_coord(tiles: list[dict[str, Any]]) -> dict[tuple[int, int], dict[str, Any]]:
    return {(tile["x"], tile["y"]): tile for tile in tiles}


def _set_tile(
    by_coord: dict[tuple[int, int], dict[str, Any]],
    size: int,
    x: int,
    y: int,
    kind: str,
    label: str,
    owner: str | None = None,
) -> None:
    if not (1 <= x <= size and 1 <= y <= size):
        return
    tile = by_coord.get((x, y))
    if tile is not None:
        tile.update(kind=kind, label=label, owner=owner)


def _anchor_origin(anchor: str, size: int, width: int, height: int) -> tuple[int, int]:
    if anchor == "north_east":
        return max(1, size - width + 1), 1
    if anchor == "south_west":
        return 1, max(1, size - height + 1)
    if anchor == "south_east":
        return max(1, size - width + 1), max(1, size - height + 1)
    return 1, 1


def _apply_rect_patch(
    by_coord: dict[tuple[int, int], dict[str, Any]],
    size: int,
    patch: dict[str, Any],
    default_label: str,
) -> None:
    kind = str(patch.get("kind", "grass"))
    label = str(patch.get("label") or default_label)
    width = max(1, int(patch.get("width", 1)))
    height = max(1, int(patch.get("height", 1)))
    start_x, start_y = _anchor_origin(str(patch.get("anchor", "north_west")), size, width, height)
    for x in range(start_x, min(size, start_x + width - 1) + 1):
        for y in range(start_y, min(size, start_y + height - 1) + 1):
            _set_tile(by_coord, size, x, y, kind, label)


def _perimeter_ring(size: int) -> list[tuple[int, int]]:
    if size < 2:
        return [(1, 1)]
    ring = [(x, 1) for x in range(1, size + 1)]
    ring += [(size, y) for y in range(2, size + 1)]
    ring += [(x, size) for x in range(size - 1, 0, -1)]
    ring += [(1, y) for y in range(size - 1, 1, -1)]
    return ring


def generate_realm_map(size: int, seed: str | None = None) -> list[dict[str, Any]]:
    del seed
    config = MAP_GENERATION.get("realm", {})
    tiles = _base_tiles(size)
    by_coord = _by_coord(tiles)

    for patch in config.get("forest_patches", []):
        forest_patch = {"kind": "forest", **patch}
        _apply_rect_patch(by_coord, size, forest_patch, "林地")

    center = max(1, (size + 1) // 2)
    center_building = config.get("center_building", {"kind": "castle", "label": "领主堡垒"})
    _set_tile(by_coord, size, center, center, str(center_building.get("kind", "castle")), str(center_building.get("label", "领主堡垒")))

    for neighbor in config.get("starting_neighbors", [{"dx": 0, "dy": 1, "kind": "homes", "label": "村舍"}]):
        x = max(1, min(size, center + int(neighbor.get("dx", 0))))
        y = max(1, min(size, center + int(neighbor.get("dy", 1))))
        if (x, y) == (center, center):
            y = min(size, center + 1) if center < size else max(1, center - 1)
        _set_tile(by_coord, size, x, y, str(neighbor.get("kind", "homes")), str(neighbor.get("label", "村舍")))

    return sanitize_realm_map(tiles)


def player_faction_static(realm_name: str) -> dict[str, Any]:
    return {
        "color": "#b88a50",
        "banner": "♜",
        "description": f"{realm_name}，玩家直接统治的领地势力。",
        "is_player": True,
    }


def player_faction_name(realm_name: Any) -> str:
    name = str(realm_name or "").strip()
    return name or "玩家"


def ensure_player_faction(factions: dict[str, Any], realm_name: Any) -> str:
    name = player_faction_name(realm_name)
    base = factions.setdefault(name, player_faction_static(name))
    if isinstance(base, dict):
        defaults = player_faction_static(name)
        for key, value in defaults.items():
            base.setdefault(key, value)
        base["is_player"] = True
    return name


def ensure_player_diplomacy_position(tiles: list[dict[str, Any]], size: int, realm_name: Any) -> list[dict[str, Any]]:
    player = player_faction_name(realm_name)
    center = max(1, (size + 1) // 2)
    by_coord = _by_coord(tiles)
    _set_tile(by_coord, size, center, center, "castle", f"{player}城堡", owner=player)
    return tiles


def generate_diplomacy_map(size: int, factions: dict[str, Any] | None = None, seed: str | None = None, player_faction: str | None = None) -> list[dict[str, Any]]:
    del seed
    config = MAP_GENERATION.get("diplomacy", {})
    tiles = _base_tiles(size)
    by_coord = _by_coord(tiles)

    terrain_labels = {"forest": "森林", "hill": "山丘", "lake": "湖泊", "river": "河流", "grass": "草地"}
    for patch in config.get("terrain_patches", []):
        kind = str(patch.get("kind", "grass"))
        if patch.get("shape") == "south_edge":
            if size >= 3:
                for x in range(3, max(3, size - 1)):
                    _set_tile(by_coord, size, x, size, kind, terrain_labels.get(kind, kind))
            continue
        _apply_rect_patch(by_coord, size, patch, terrain_labels.get(kind, kind))

    faction_items = [item for item in (factions or FACTIONS).keys() if item != player_faction]
    perimeter = _perimeter_ring(size)
    placement = config.get("faction_placement", {})
    cycle = list(placement.get("settlement_cycle", ["village", "castle", "town", "slum"]))
    step = max(1, len(perimeter) // len(faction_items)) if faction_items else 1
    for index, faction in enumerate(faction_items):
        x, y = perimeter[(index * step) % len(perimeter)]
        kind = str(cycle[index % len(cycle)])
        label = DIPLOMACY_SETTLEMENT_LABELS.get(kind, kind)
        _set_tile(by_coord, size, x, y, kind, f"{faction}{label}", owner=faction)

    if player_faction:
        ensure_player_diplomacy_position(tiles, size, player_faction)
    return tiles


def sanitize_realm_map(tiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized = deepcopy(tiles)
    faction_names = set(FACTIONS.keys())
    for tile in sanitized:
        tile.setdefault("owner", None)
        label = str(tile.get("label", ""))
        has_faction_label = any(faction in label for faction in faction_names)
        if tile.get("owner") or tile.get("kind") in REALM_FORBIDDEN_KINDS or (has_faction_label and label != "领主堡垒"):
            tile.update(kind="grass", label="草地", owner=None)
        else:
            tile["owner"] = None
    return sanitized


def validate_generated_maps(
    realm_map: list[dict[str, Any]],
    diplomacy_map: list[dict[str, Any]],
    size: int,
    known_factions: dict[str, Any] | None = None,
) -> None:
    if len(realm_map) != size * size:
        raise ValueError("领地地图尺寸不正确")
    if len(diplomacy_map) != size * size:
        raise ValueError("外交地图尺寸不正确")
    expected_coords = {(x, y) for y in range(1, size + 1) for x in range(1, size + 1)}
    realm_coords = {(int(tile.get("x", 0)), int(tile.get("y", 0))) for tile in realm_map}
    diplomacy_coords = {(int(tile.get("x", 0)), int(tile.get("y", 0))) for tile in diplomacy_map}
    if realm_coords != expected_coords:
        raise ValueError("领地地图坐标不完整或超出范围")
    if diplomacy_coords != expected_coords:
        raise ValueError("外交地图坐标不完整或超出范围")
    unknown_realm_kinds = {str(tile.get("kind")) for tile in realm_map} - set(MAP_TILE_KINDS.keys())
    if unknown_realm_kinds:
        raise ValueError(f"领地地图存在未知地块类型: {sorted(unknown_realm_kinds)}")
    unknown_diplomacy_kinds = {str(tile.get("kind")) for tile in diplomacy_map} - set(DIPLOMACY_TILE_KINDS.keys())
    if unknown_diplomacy_kinds:
        raise ValueError(f"外交地图存在未知地块类型: {sorted(unknown_diplomacy_kinds)}")
    center = max(1, (size + 1) // 2)
    center_tile = next((tile for tile in realm_map if tile.get("x") == center and tile.get("y") == center), None)
    if not center_tile or center_tile.get("kind") != "castle" or center_tile.get("label") != "领主堡垒":
        raise ValueError("领地地图中心必须是领主堡垒")
    if any(tile.get("owner") for tile in realm_map):
        raise ValueError("领地地图不得出现外交势力归属")
    forbidden_realm = {tile.get("kind") for tile in realm_map} & REALM_FORBIDDEN_KINDS
    if forbidden_realm:
        raise ValueError(f"领地地图不得出现外交大地图地块: {sorted(forbidden_realm)}")
    diplomacy_economy_kinds = {tile.get("kind") for tile in diplomacy_map} & DIPLOMACY_ECONOMY_BUILDING_KINDS
    if diplomacy_economy_kinds:
        raise ValueError(f"外交地图不得出现领地经营建筑地块: {sorted(diplomacy_economy_kinds)}")
    known = set((known_factions or FACTIONS).keys())
    unknown_owners = {str(tile.get("owner")) for tile in diplomacy_map if tile.get("owner") and tile.get("owner") not in known}
    if unknown_owners:
        raise ValueError(f"外交地图存在未知势力归属: {sorted(unknown_owners)}")
