from __future__ import annotations

from conftest import start_game
from app.engine.state import normalize_state


def test_realm_map_and_diplomacy_map_are_separate(client):
    state = start_game(client)

    assert len(state["map"]) == 100
    assert len(state["diplomacy_map"]) == 100
    assert state["map_size"] == 10
    assert state["diplomacy_map_size"] == 10

    assert all(tile.get("owner") is None for tile in state["map"])
    owned_diplomacy_tiles = [tile for tile in state["diplomacy_map"] if tile.get("owner")]
    assert {tile["owner"] for tile in owned_diplomacy_tiles} == set(state["diplomacy"])

    forbidden_realm_buildings = {
        "farm",
        "lumberyard",
        "quarry",
        "blacksmith",
        "hunting_lodge",
        "ranch",
        "handicraft_workshop",
        "shop",
        "tavern",
        "monastery",
        "prison",
        "barracks",
        "wall",
        "hut_yard",
        "townhouses",
        "manor",
    }
    assert forbidden_realm_buildings.isdisjoint({tile["kind"] for tile in state["diplomacy_map"]})


def test_catalog_separates_realm_and_diplomacy_tile_kinds(client):
    response = client.get("/api/catalog")
    assert response.status_code == 200, response.text
    catalog = response.json()

    assert "farm" in catalog["map_tile_kinds"]
    assert "lumberyard" in catalog["map_tile_kinds"]
    assert "blacksmith" in catalog["map_tile_kinds"]
    assert "town" not in catalog["map_tile_kinds"]
    assert "village" not in catalog["map_tile_kinds"]
    assert "slum" not in catalog["map_tile_kinds"]

    assert {"town", "castle", "village", "slum", "forest", "grass", "lake", "river", "hill"}.issubset(
        catalog["diplomacy_tile_kinds"]
    )


def test_building_mutation_updates_only_realm_map(client):
    start_game(client)
    before = client.get("/api/state").json()["state"]
    diplomacy_before = list(before["diplomacy_map"])

    response = client.post("/api/state/buildings", json={"building": "农田", "action": "build", "x": 3, "y": 3})
    assert response.status_code == 200, response.text
    state = response.json()["state"]

    realm_tile = next(tile for tile in state["map"] if tile["x"] == 3 and tile["y"] == 3)
    assert realm_tile["kind"] == "farm"
    assert realm_tile["label"] == "农田"
    assert state["diplomacy_map"] == diplomacy_before


def test_faction_detail_scans_diplomacy_map_not_realm_map(client):
    state = start_game(client)
    faction = next(iter(state["diplomacy"]))
    expected = [tile for tile in state["diplomacy_map"] if tile.get("owner") == faction]

    response = client.get("/api/state/diplomacy")
    assert response.status_code == 200, response.text
    detail = response.json()["factions"][faction]

    assert detail["owned_tile_count"] == len(expected)
    assert detail["owned_tiles"] == expected
    assert "state" in detail
    assert {"resources", "army", "army_status", "buildings", "workforce", "laws"}.issubset(detail["state"])
    assert "gold" in detail["state"]["resources"]
    assert "food" in detail["state"]["resources"]
    assert "infantry" in detail["state"]["army"]


def test_faction_states_include_player_and_foreign_operational_ledgers(client):
    state = start_game(client)

    assert "北境" in state["faction_states"]
    assert state["faction_states"]["北境"]["is_player"] is True
    assert state["faction_states"]["北境"]["resources"]["gold"] == state["resources"]["gold"]
    assert state["faction_states"]["北境"]["army"] == state["army"]

    foreign = next(faction for faction in state["diplomacy"] if faction != "北境")
    ledger = state["faction_states"][foreign]
    assert ledger["is_player"] is False
    assert ledger["resources"]["gold"] > 0
    assert ledger["resources"]["food"] > 0
    assert set(ledger["army"]) >= {"infantry", "archers", "cavalry"}
    assert ledger["territory"]["owned_tile_count"] == len([tile for tile in state["diplomacy_map"] if tile.get("owner") == foreign])


def test_normalize_removes_foreign_estates_from_realm_map():
    state = {
        "resources": {"gold": 500, "food": 500, "wood": 0, "stone": 0, "population": 100, "morale": 50, "authority": 50},
        "changes": {},
        "diplomacy": {"血鸦": "敌对"},
        "map_size": 2,
        "map": [
            {"x": 1, "y": 1, "kind": "castle", "label": "领主堡垒", "owner": None},
            {"x": 2, "y": 1, "kind": "village", "label": "血鸦农村", "owner": "血鸦"},
            {"x": 1, "y": 2, "kind": "town", "label": "错误城镇", "owner": None},
            {"x": 2, "y": 2, "kind": "grass", "label": "草地"},
        ],
    }

    normalize_state(state)

    assert all(tile.get("owner") is None for tile in state["map"])
    assert all(tile["kind"] not in {"town", "village", "slum"} for tile in state["map"])
    center = (state["map_size"] + 1) // 2
    assert next(tile for tile in state["map"] if tile["x"] == center and tile["y"] == center)["kind"] == "castle"


def test_normalize_prunes_catalog_only_starting_buildings():
    state = {
        "resources": {"gold": 500, "food": 500, "wood": 0, "stone": 0, "population": 100, "morale": 50, "authority": 50},
        "changes": {},
        "diplomacy": {"血鸦": "敌对"},
        "turn": 1,
        "map_size": 10,
        "map": [
            {"x": x, "y": y, "kind": "grass", "label": "草地", "owner": None}
            for y in range(1, 11)
            for x in range(1, 11)
        ],
        "buildings": {"领主堡垒": 1, "村舍": 1, "镇屋": 1, "手工作坊": 1, "商店": 1, "宅邸": 1},
    }
    next(tile for tile in state["map"] if tile["x"] == 5 and tile["y"] == 5).update(kind="castle", label="领主堡垒")
    next(tile for tile in state["map"] if tile["x"] == 5 and tile["y"] == 6).update(kind="homes", label="村舍")

    normalize_state(state)

    assert state["buildings"] == {"领主堡垒": 1, "村舍": 1}
