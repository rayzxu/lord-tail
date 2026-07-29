from __future__ import annotations

from app.catalog import BUILDINGS, MAP_TILE_KINDS
from conftest import start_game


def test_state_api_resources_population_and_buildings(client):
    start_game(client)

    response = client.post("/api/state/resources", json={"changes": {"gold": 25, "population": 5}})
    assert response.status_code == 200, response.text
    state = response.json()["state"]
    assert state["resources"]["gold"] >= 525
    assert state["resources"]["population"] == sum(
        item["population"] for item in state["demographics"]["classes"].values()
    )

    response = client.post("/api/state/morale", json={"delta": -10})
    assert response.status_code == 200, response.text
    assert response.json()["state"]["resources"]["morale"] == 60

    response = client.post("/api/state/buildings", json={"building": "窝棚区", "action": "build", "count": 1})
    assert response.status_code == 200, response.text
    housing = response.json()["state"]["demographics"]["housing"]["by_type"]
    assert housing["hut"]["capacity"] >= 112


def test_state_api_army_and_diplomacy(client):
    start_game(client)

    response = client.post("/api/state/army", json={"unit": "步兵", "value": 12})
    assert response.status_code == 200, response.text
    state = response.json()["state"]
    assert state["army"]["infantry"] == 12
    assert state["faction_states"]["北境"]["army"]["infantry"] == 12

    response = client.post("/api/state/diplomacy", json={"faction": "金鳞", "status": "友善"})
    assert response.status_code == 200, response.text
    entry = response.json()["state"]["diplomacy"]["金鳞"]
    assert entry["stance"] == "友善"
    assert entry["relation"] == 70


def test_state_api_player_faction_resources_mirror_realm_resources(client):
    start_game(client)

    response = client.post("/api/state/resources", json={"changes": {"gold": 25, "food": -10}})
    assert response.status_code == 200, response.text
    state = response.json()["state"]

    assert state["faction_states"]["北境"]["resources"]["gold"] == state["resources"]["gold"]
    assert state["faction_states"]["北境"]["resources"]["food"] == state["resources"]["food"]


def test_new_oppressive_buildings_are_catalogued_and_buildable(client):
    start_game(client)
    expected = {
        "punishment_pillory": ("露天刑架/羞辱柱", "🩸", (2, 2)),
        "brothel_tavern": ("妓院/酒馆", "🎪", (3, 2)),
        "public_breeding_house": ("公共繁育所", "🛏️", (4, 2)),
        "lord_dungeon": ("领主专属地牢/调教室", "⛓️", (6, 2)),
    }

    for building_id, (name, icon, (x, y)) in expected.items():
        building = BUILDINGS[building_id]
        assert building["name"] == name
        assert MAP_TILE_KINDS[building["tile_kind"]]["icon"] == icon

        response = client.post(
            "/api/state/buildings",
            json={"building": building_id, "action": "build", "count": 1, "x": x, "y": y},
        )

        assert response.status_code == 200, response.text
        state = response.json()["state"]
        assert state["buildings"][name] == 1
        tile = next(tile for tile in state["map"] if tile["x"] == x and tile["y"] == y)
        assert tile["kind"] == building["tile_kind"]
        assert tile["label"] == name
