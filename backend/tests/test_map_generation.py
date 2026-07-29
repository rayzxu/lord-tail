from __future__ import annotations

from app.catalog import FACTIONS
from app.engine.mapgen import (
    DIPLOMACY_ECONOMY_BUILDING_KINDS,
    REALM_FORBIDDEN_KINDS,
    generate_diplomacy_map,
    generate_realm_map,
    sanitize_realm_map,
)


def _tile_at(tiles: list[dict], x: int, y: int) -> dict:
    return next(tile for tile in tiles if tile["x"] == x and tile["y"] == y)


def test_generate_realm_map_places_lord_castle_at_center():
    tiles = generate_realm_map(10)
    center = _tile_at(tiles, 5, 5)

    assert len(tiles) == 100
    assert center["kind"] == "castle"
    assert center["label"] == "领主堡垒"
    assert center["owner"] is None
    assert _tile_at(tiles, 5, 6)["kind"] == "homes"
    assert "forest" in {tile["kind"] for tile in tiles}
    assert all(tile.get("owner") is None for tile in tiles)
    assert not ({tile["kind"] for tile in tiles} & REALM_FORBIDDEN_KINDS)


def test_generate_diplomacy_map_places_large_terrain_and_factions():
    tiles = generate_diplomacy_map(10, FACTIONS)
    kinds = {tile["kind"] for tile in tiles}

    assert len(tiles) == 100
    assert {"hill", "lake", "river"}.issubset(kinds)
    assert not (kinds & DIPLOMACY_ECONOMY_BUILDING_KINDS)
    for faction in FACTIONS:
        owned = [tile for tile in tiles if tile.get("owner") == faction]
        assert owned, faction
        assert any(tile["kind"] in {"town", "castle", "village", "slum"} for tile in owned)


def test_sanitize_realm_map_removes_diplomacy_tiles_but_keeps_lord_castle():
    tiles = [
        {"x": 1, "y": 1, "kind": "castle", "label": "领主堡垒", "owner": None},
        {"x": 2, "y": 1, "kind": "castle", "label": "血鸦城堡", "owner": "血鸦"},
        {"x": 1, "y": 2, "kind": "river", "label": "河流", "owner": None},
        {"x": 2, "y": 2, "kind": "town", "label": "金鳞城镇", "owner": None},
    ]

    sanitized = sanitize_realm_map(tiles)

    assert sanitized[0]["kind"] == "castle"
    assert sanitized[0]["label"] == "领主堡垒"
    assert all(tile.get("owner") is None for tile in sanitized)
    assert sanitized[1]["kind"] == "grass"
    assert sanitized[2]["kind"] == "grass"
    assert sanitized[3]["kind"] == "grass"


def test_game_start_uses_generated_realm_and_diplomacy_maps(client):
    response = client.post("/api/game/start", json={
        "lord_name": "Ray",
        "lord_gender": "未说明",
        "realm_name": "北境",
        "appearance": "",
        "personality": "",
        "talents": [{"id": "harvest_hand"}, {"id": "charismatic_lord"}],
    })
    assert response.status_code == 200, response.text
    state = response.json()["state"]

    realm_kinds = {tile["kind"] for tile in state["map"]}
    diplomacy_kinds = {tile["kind"] for tile in state["diplomacy_map"]}
    center = _tile_at(state["map"], 5, 5)

    assert center["kind"] == "castle"
    assert center["label"] == "领主堡垒"
    diplomacy_center = _tile_at(state["diplomacy_map"], 5, 5)
    assert diplomacy_center["kind"] == "castle"
    assert diplomacy_center["owner"] == "北境"
    assert diplomacy_center["label"] == "北境城堡"
    assert state["factions"]["北境"]["is_player"] is True
    assert state["diplomacy"]["北境"]["stance"] == "己方"
    assert state["buildings"] == {"领主堡垒": 1, "村舍": 1}
    assert all(tile.get("owner") is None for tile in state["map"])
    assert not (realm_kinds & REALM_FORBIDDEN_KINDS)
    assert {"hill", "lake", "river"}.issubset(diplomacy_kinds)
    assert not (diplomacy_kinds & DIPLOMACY_ECONOMY_BUILDING_KINDS)


def test_game_start_accepts_custom_neighbors_and_setup_maps(client):
    realm_map = generate_realm_map(10)
    _tile_at(realm_map, 2, 2).update(kind="farm", label="农田", owner=None)
    diplomacy_map = generate_diplomacy_map(10, {"灰狼": {}, "盐港": {}})
    _tile_at(diplomacy_map, 10, 10).update(kind="castle", label="灰狼城堡", owner="灰狼")

    response = client.post("/api/game/start", json={
        "lord_name": "Ray",
        "lord_gender": "未说明",
        "realm_name": "北境",
        "appearance": "",
        "personality": "",
        "talents": [{"id": "harvest_hand"}, {"id": "charismatic_lord"}],
        "map_size": 10,
        "factions": {
            "灰狼": {"color": "#777777", "banner": "🐺", "description": "北方山隘的狼旗邻邦。"},
            "盐港": {"color": "#6688aa", "banner": "⚓", "description": "依赖盐与船税的港口城邦。"},
        },
        "diplomacy": {
            "灰狼": {"stance": "敌对", "relation": -70, "at_war": False, "treaties": []},
            "盐港": {"stance": "友善", "relation": 65, "at_war": False, "treaties": []},
        },
        "realm_map": realm_map,
        "diplomacy_map": diplomacy_map,
    })

    assert response.status_code == 200, response.text
    state = response.json()["state"]

    assert state["factions"]["灰狼"]["banner"] == "🐺"
    assert state["diplomacy"]["灰狼"]["stance"] == "敌对"
    assert state["diplomacy"]["盐港"]["relation"] == 65
    assert state["diplomacy"]["北境"]["stance"] == "己方"
    assert _tile_at(state["map"], 2, 2)["kind"] == "farm"
    assert state["buildings"] == {"农田": 1, "领主堡垒": 1, "村舍": 1}
    assert _tile_at(state["diplomacy_map"], 5, 5)["owner"] == "北境"
    assert _tile_at(state["diplomacy_map"], 10, 10)["owner"] == "灰狼"
